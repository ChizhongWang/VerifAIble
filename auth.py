"""
Google OAuth 2.0 认证模块
"""
from flask import Blueprint, redirect, url_for, session, request, jsonify
from authlib.integrations.flask_client import OAuth
from models import db, User
from datetime import datetime
import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)

# 初始化OAuth
oauth = OAuth()

def init_oauth(app):
    """初始化OAuth配置"""
    oauth.init_app(app)

    # Google OAuth配置
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

# 加密密钥 - 用于加密存储用户的API密钥
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', Fernet.generate_key().decode())
cipher_suite = Fernet(ENCRYPTION_KEY.encode())

def encrypt_api_key(api_key: str) -> str:
    """加密API密钥"""
    if not api_key:
        return None
    return cipher_suite.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    """解密API密钥"""
    if not encrypted_key:
        return None
    return cipher_suite.decrypt(encrypted_key.encode()).decode()

@auth_bp.route('/login')
def login():
    """开始Google OAuth登录流程"""
    redirect_uri = url_for('auth.callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def callback():
    """Google OAuth回调"""
    try:
        # 获取access token
        token = oauth.google.authorize_access_token()

        # 获取用户信息
        user_info = token.get('userinfo')

        if not user_info:
            return jsonify({'error': 'Failed to get user info'}), 400

        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')

        # 查找或创建用户
        user = User.query.filter_by(google_id=google_id).first()

        if not user:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture=picture
            )
            db.session.add(user)
        else:
            # 更新用户信息
            user.name = name
            user.picture = picture
            user.last_login = datetime.utcnow()

        db.session.commit()

        # 保存到session
        session['user_id'] = user.id
        session['user_email'] = user.email
        session['user_name'] = user.name
        session['user_picture'] = user.picture

        logger.info(f"用户登录成功: {email}")

        # 重定向到主页
        return redirect(url_for('index'))

    except Exception as e:
        logger.error(f"登录失败: {e}")
        return jsonify({'error': 'Login failed', 'details': str(e)}), 500

@auth_bp.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('index'))

@auth_bp.route('/user/info')
def user_info():
    """获取当前用户信息"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(user.to_dict())

@auth_bp.route('/user/api-key', methods=['GET', 'POST'])
def api_key():
    """获取或设置用户的OpenAI API密钥"""
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'POST':
        # 保存API密钥
        data = request.json
        api_key = data.get('api_key', '')

        if not api_key.startswith('sk-'):
            return jsonify({'error': 'Invalid API key format'}), 400

        # 加密并保存
        user.openai_api_key = encrypt_api_key(api_key)
        db.session.commit()

        logger.info(f"用户 {user.email} 已设置API密钥")
        return jsonify({'success': True, 'message': 'API key saved'})

    else:
        # 获取API密钥（返回是否已设置）
        return jsonify({
            'has_api_key': bool(user.openai_api_key)
        })

def get_user_api_key(user_id: int) -> str:
    """获取用户的解密后的API密钥"""
    user = User.query.get(user_id)
    if not user or not user.openai_api_key:
        return None
    return decrypt_api_key(user.openai_api_key)

def require_auth(f):
    """装饰器：要求用户登录"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)

    return decorated_function

def require_api_key(f):
    """装饰器：要求用户已设置API密钥"""
    from functools import wraps

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401

        user = User.query.get(session['user_id'])
        if not user or not user.openai_api_key:
            return jsonify({'error': 'OpenAI API key not configured'}), 403

        return f(*args, **kwargs)

    return decorated_function
