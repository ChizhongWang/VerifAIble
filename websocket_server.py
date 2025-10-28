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

@app.route('/user/emails', methods=['GET', 'POST'])
@require_auth
def manage_emails():
    """管理用户通知邮箱"""
    from models import User
    import json

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'GET':
        # 获取邮箱列表
        emails = []
        if user.notification_emails:
            try:
                emails = json.loads(user.notification_emails)
            except:
                emails = []

        return jsonify({
            'emails': emails,
            'default_email': user.email  # Google OAuth邮箱
        })

    elif request.method == 'POST':
        # 更新邮箱列表
        data = request.json
        emails = data.get('emails', [])

        # 验证邮箱格式
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for email in emails:
            if not re.match(email_pattern, email):
                return jsonify({'error': f'Invalid email: {email}'}), 400

        # 保存
        user.notification_emails = json.dumps(emails)
        db.session.commit()

        logger.info(f"用户 {user.email} 更新了通知邮箱")
        return jsonify({'success': True, 'emails': emails})


@app.route('/deep_search', methods=['POST'])
@require_auth
def deep_search():
    """执行深度搜索任务"""
    from models import Task
    from intent_api import IntentRecognitionAPI
    import threading
    import json

    try:
        data = request.json
        query = data.get('query', '').strip()

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        user_id = session['user_id']

        # 1. 调用意图识别获取目标URL
        intent_api = IntentRecognitionAPI()
        intent_result = intent_api.recognize_intent(query, top_k=1, return_details=True)

        if intent_result['status'] != 'success':
            return jsonify({'error': 'Intent recognition failed'}), 500

        target_url = intent_result['result']['url']

        # 2. 创建任务记录
        task = Task(
            user_id=user_id,
            query=query,
            target_url=target_url,
            status='pending'
        )
        db.session.add(task)
        db.session.commit()

        task_id = task.id

        logger.info(f"创建深度搜索任务 {task_id}: {query} -> {target_url}")

        # 3. 异步执行任务
        thread = threading.Thread(
            target=_execute_deep_search_task,
            args=(task_id, query, target_url, user_id),
            daemon=True
        )
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'target_url': target_url,
            'message': '任务已创建，正在后台执行中...'
        })

    except Exception as e:
        logger.error(f"创建深度搜索任务失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


def _execute_deep_search_task(task_id: int, query: str, target_url: str, user_id: int):
    """后台执行深度搜索任务"""
    from models import Task, User
    from browser_agent import BrowserAgent
    from email_service import EmailService
    import json
    import asyncio

    with app.app_context():
        try:
            # 更新任务状态
            task = Task.query.get(task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return

            task.status = 'processing'
            task.started_at = datetime.utcnow()
            db.session.commit()

            # 获取用户API Key
            user_api_key = get_user_api_key(user_id)
            if not user_api_key:
                task.status = 'failed'
                task.error_message = 'User API key not configured'
                db.session.commit()
                return

            # 执行浏览器任务
            agent = BrowserAgent(api_key=user_api_key, max_steps=10)
            result = asyncio.run(agent.execute_task(query, target_url, task_id))

            if result['success']:
                # 任务成功
                task.status = 'completed'
                task.summary = result.get('summary', '')
                task.source_url = result.get('source_url', '')
                task.citations = json.dumps(result.get('citations', []))
                task.steps = json.dumps(result.get('steps', []))
                task.step_count = len(result.get('steps', []))
                task.downloaded_files = json.dumps(result.get('downloaded_files', []))  # 🆕 保存下载文件列表
                task.report_html_path = result.get('report_html_path', '')
                task.completed_at = datetime.utcnow()

                # 生成语音汇报提示词
                task.briefing_prompt = _generate_briefing_prompt(task, query, result)

                db.session.commit()

                # 发送邮件通知
                _send_task_notification_email(task_id, user_id, result)

            else:
                # 任务失败
                task.status = 'failed'
                task.error_message = result.get('error', 'Unknown error')
                task.completed_at = datetime.utcnow()
                db.session.commit()

                logger.error(f"任务 {task_id} 执行失败: {result.get('error')}")

        except Exception as e:
            logger.error(f"执行深度搜索任务 {task_id} 出错: {e}")
            import traceback
            traceback.print_exc()

            # 更新任务状态为失败
            task = Task.query.get(task_id)
            if task:
                task.status = 'failed'
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()
                db.session.commit()


def _generate_briefing_prompt(task, query: str, result: Dict) -> str:
    """生成语音汇报提示词"""
    summary = result.get('summary', '')
    source_url = result.get('source_url', '')

    prompt = f"""你是 VerifAIble 智能助手。用户刚刚接听了一个"未接来电"，
你需要向他汇报之前完成的深度研究任务。

【任务背景】
用户在 {task.created_at.strftime('%Y-%m-%d %H:%M')} 提问：
"{query}"

【研究结果】
你已经通过浏览器自动化访问了 {source_url}，找到了以下信息：

{summary}

【汇报要求】
1. 简洁专业，1-2分钟内汇报完成
2. 突出关键发现和数据
3. 提及信息来源（{source_url}）
4. 询问用户是否需要更多细节
5. 提醒用户邮箱中有详细报告和截图

现在开始汇报。
"""
    return prompt


def _send_task_notification_email(task_id: int, user_id: int, result: dict):
    """发送任务完成通知邮件（使用 EmailAgent）"""
    from models import Task, User
    from email_agent import EmailAgent
    import json

    try:
        task = Task.query.get(task_id)
        user = User.query.get(user_id)

        if not task or not user:
            return

        # 获取通知邮箱列表
        emails = []
        if user.notification_emails:
            try:
                emails = json.loads(user.notification_emails)
            except:
                pass

        # 如果没有配置通知邮箱，使用Google OAuth邮箱
        if not emails:
            emails = [user.email]

        # 准备用户名
        user_name = user.name or user.email.split('@')[0]

        # 创建邮件代理
        email_agent = EmailAgent()

        # 为每个邮箱发送邮件
        all_success = True
        for recipient_email in emails:
            success = email_agent.send_task_result(
                task_result=result,
                recipient_email=recipient_email,
                user_name=user_name,
                include_downloads=True,  # 附加下载的PDF等文件
                include_screenshots=True  # 附加截图（最多5张）
            )

            if not success:
                all_success = False
                logger.error(f"发送邮件到 {recipient_email} 失败")

        if all_success:
            task.email_sent = True
            db.session.commit()
            logger.info(f"任务 {task_id} 的通知邮件已发送到 {len(emails)} 个邮箱")
        else:
            logger.error(f"任务 {task_id} 的部分邮件发送失败")

    except Exception as e:
        logger.error(f"发送任务通知邮件失败: {e}")
        import traceback
        traceback.print_exc()


@app.route('/tasks/<int:task_id>')
@require_auth
def get_task(task_id):
    """获取任务详情"""
    from models import Task
    import json

    task = Task.query.get(task_id)

    if not task or task.user_id != session['user_id']:
        return jsonify({'error': 'Task not found'}), 404

    task_dict = task.to_dict()

    # 解析 steps 和 citations
    if task.steps:
        try:
            task_dict['steps'] = json.loads(task.steps)
        except:
            task_dict['steps'] = []

    if task.citations:
        try:
            task_dict['citations'] = json.loads(task.citations)
        except:
            task_dict['citations'] = []

    return jsonify(task_dict)


@app.route('/tasks/list')
@require_auth
def list_tasks():
    """获取用户的任务列表"""
    from models import Task

    tasks = Task.query.filter_by(
        user_id=session['user_id']
    ).order_by(Task.created_at.desc()).limit(50).all()

    return jsonify({
        'tasks': [task.to_dict() for task in tasks]
    })


@app.route('/tasks/<int:task_id>/mark_read', methods=['POST'])
@require_auth
def mark_task_read(task_id):
    """标记任务为已读（已接听）"""
    from models import Task

    task = Task.query.get(task_id)

    if not task or task.user_id != session['user_id']:
        return jsonify({'error': 'Task not found'}), 404

    task.is_read = True
    db.session.commit()

    return jsonify({'success': True})


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
