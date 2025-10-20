"""
OpenAI Realtime API WebSocket Server
使用WebSocket连接,支持意图识别工具调用
多用户认证,数据库存储
"""

from flask import Flask, send_from_directory, jsonify, session, redirect, url_for
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
CORS(app)

# Flask配置
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24).hex())
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///uniagent.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = os.getenv('HTTPS', 'False').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# 初始化数据库
from models import db
db.init_app(app)

# 初始化认证
from auth import auth_bp, init_oauth, get_user_api_key, require_auth, require_api_key
init_oauth(app)
app.register_blueprint(auth_bp, url_prefix='/auth')

# 在应用上下文中创建数据库表
with app.app_context():
    db.create_all()
    logger.info("数据库表已创建")

@app.route('/')
def index():
    """提供WebSocket版本的前端页面"""
    # 检查用户是否登录
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    # 检查用户是否配置了API密钥
    user_api_key = get_user_api_key(session['user_id'])
    if not user_api_key:
        return redirect(url_for('settings_page'))

    return send_from_directory('static', 'websocket.html')

@app.route('/login')
def login_page():
    """登录页面"""
    if 'user_id' in session:
        return redirect(url_for('index'))
    return send_from_directory('static', 'login.html')

@app.route('/settings')
def settings_page():
    """设置页面"""
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return send_from_directory('static', 'settings.html')

@app.route('/api_key')
@require_api_key
def get_api_key():
    """返回用户的API key供前端WebSocket连接使用"""
    user_api_key = get_user_api_key(session['user_id'])
    return jsonify({
        "api_key": user_api_key
    })

@app.route('/recognize_intent', methods=['POST'])
@require_auth
def recognize_intent():
    """意图识别API端点"""
    from flask import request
    from intent_api import IntentRecognitionAPI
    from models import Conversation, ToolCall
    from datetime import datetime
    import json

    try:
        data = request.json
        query = data.get('query', '')
        top_k = data.get('top_k', 3)
        session_id = data.get('session_id')  # 前端传来的会话ID

        if not query:
            return jsonify({"error": "query is required"}), 400

        logger.info(f"用户 {session['user_id']} 识别意图: {query}")

        intent_api = IntentRecognitionAPI()
        result = intent_api.recognize_intent(
            query=query,
            top_k=top_k,
            return_details=True
        )

        # 记录工具调用
        if session_id:
            conversation = Conversation.query.filter_by(
                user_id=session['user_id'],
                session_id=session_id
            ).first()

            if conversation:
                tool_call = ToolCall(
                    conversation_id=conversation.id,
                    tool_name='recognize_intent',
                    arguments=json.dumps({'query': query, 'top_k': top_k}),
                    result=json.dumps(result)
                )
                db.session.add(tool_call)
                db.session.commit()

        logger.info(f"识别结果: {result}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"意图识别出错: {e}")
        return jsonify({
            "error": "Intent recognition failed",
            "details": str(e)
        }), 500

@app.route('/conversation/start', methods=['POST'])
@require_auth
def start_conversation():
    """开始新对话"""
    from flask import request
    from models import Conversation
    import uuid

    try:
        session_id = str(uuid.uuid4())

        conversation = Conversation(
            user_id=session['user_id'],
            session_id=session_id
        )
        db.session.add(conversation)
        db.session.commit()

        logger.info(f"用户 {session['user_id']} 开始对话: {session_id}")

        return jsonify({
            'session_id': session_id,
            'conversation_id': conversation.id
        })

    except Exception as e:
        logger.error(f"创建对话失败: {e}")
        return jsonify({'error': 'Failed to start conversation'}), 500

@app.route('/conversation/end', methods=['POST'])
@require_auth
def end_conversation():
    """结束对话"""
    from flask import request
    from models import Conversation
    from datetime import datetime

    try:
        data = request.json
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({'error': 'session_id required'}), 400

        conversation = Conversation.query.filter_by(
            user_id=session['user_id'],
            session_id=session_id
        ).first()

        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404

        conversation.ended_at = datetime.utcnow()
        if conversation.started_at:
            duration = (conversation.ended_at - conversation.started_at).total_seconds()
            conversation.duration_seconds = int(duration)

        db.session.commit()

        logger.info(f"用户 {session['user_id']} 结束对话: {session_id}")

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"结束对话失败: {e}")
        return jsonify({'error': 'Failed to end conversation'}), 500

@app.route('/conversation/message', methods=['POST'])
@require_auth
def save_message():
    """保存对话消息"""
    from flask import request
    from models import Conversation, Message

    try:
        data = request.json
        session_id = data.get('session_id')
        role = data.get('role')  # 'user' or 'assistant'
        content = data.get('content')

        if not all([session_id, role, content]):
            return jsonify({'error': 'Missing required fields'}), 400

        conversation = Conversation.query.filter_by(
            user_id=session['user_id'],
            session_id=session_id
        ).first()

        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404

        message = Message(
            conversation_id=conversation.id,
            role=role,
            content=content
        )
        db.session.add(message)
        db.session.commit()

        return jsonify({'success': True, 'message_id': message.id})

    except Exception as e:
        logger.error(f"保存消息失败: {e}")
        return jsonify({'error': 'Failed to save message'}), 500

@app.route('/conversation/history')
@require_auth
def conversation_history():
    """获取用户的对话历史"""
    from models import Conversation

    try:
        conversations = Conversation.query.filter_by(
            user_id=session['user_id']
        ).order_by(Conversation.started_at.desc()).limit(50).all()

        return jsonify({
            'conversations': [conv.to_dict() for conv in conversations]
        })

    except Exception as e:
        logger.error(f"获取对话历史失败: {e}")
        return jsonify({'error': 'Failed to get history'}), 500

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "service": "OpenAI Realtime WebSocket Server"
    })

if __name__ == '__main__':
    if not OPENAI_API_KEY:
        logger.error("缺少OPENAI_API_KEY环境变量")
        exit(1)

    port = 3001  # WebSocket服务器使用3001端口
    logger.info(f"启动WebSocket服务器，端口: {port}")
    logger.info(f"访问 http://localhost:{port} 开始使用")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.getenv("DEBUG", "False").lower() == "true"
    )
