"""
数据库模型定义
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    """用户表"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(255))
    picture = db.Column(db.String(500))  # Google头像URL
    openai_api_key = db.Column(db.String(500))  # 加密存储
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

    # 声纹识别相关字段
    voiceprint_profile = db.Column(db.Text)  # JSON格式存储声纹特征向量
    call_mode = db.Column(db.String(20))  # 'earpiece' or 'speaker'
    voiceprint_enabled = db.Column(db.Boolean, default=False)  # 是否启用声纹验证
    voiceprint_enrolled_at = db.Column(db.DateTime)  # 声纹注册时间

    # 通知邮箱（支持多个）
    notification_emails = db.Column(db.Text)  # JSON数组格式，如["user@example.com", "backup@example.com"]

    # 关系
    conversations = db.relationship('Conversation', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    tasks = db.relationship('Task', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'picture': self.picture,
            'created_at': self.created_at.isoformat(),
            'has_api_key': bool(self.openai_api_key),
            'call_mode': self.call_mode,
            'voiceprint_enabled': self.voiceprint_enabled,
            'has_voiceprint': bool(self.voiceprint_profile),
            'voiceprint_enrolled_at': self.voiceprint_enrolled_at.isoformat() if self.voiceprint_enrolled_at else None
        }


class Conversation(db.Model):
    """对话记录表"""
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_id = db.Column(db.String(64), index=True)  # WebSocket会话ID
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)  # 通话时长（秒）

    # 关系
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')
    tool_calls = db.relationship('ToolCall', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'duration_seconds': self.duration_seconds,
            'message_count': self.messages.count(),
            'tool_call_count': self.tool_calls.count()
        }


class Message(db.Model):
    """消息记录表"""
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text)  # 转录文本
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat()
        }


class ToolCall(db.Model):
    """工具调用记录表"""
    __tablename__ = 'tool_calls'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    tool_name = db.Column(db.String(100), nullable=False)
    arguments = db.Column(db.Text)  # JSON格式
    result = db.Column(db.Text)  # JSON格式
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'tool_name': self.tool_name,
            'arguments': self.arguments,
            'result': self.result,
            'timestamp': self.timestamp.isoformat()
        }


class Task(db.Model):
    """深度搜索任务表"""
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)

    # 任务基本信息
    query = db.Column(db.Text, nullable=False)  # 用户原始问题
    target_url = db.Column(db.String(500))  # 意图识别返回的目标URL
    status = db.Column(db.String(20), default='pending', index=True)  # pending/processing/completed/failed

    # 任务结果
    summary = db.Column(db.Text)  # AI生成的摘要答案
    source_url = db.Column(db.String(500))  # 最终信息源URL（可能与target_url不同）
    citations = db.Column(db.Text)  # JSON数组，需要高亮的文本片段
    report_html_path = db.Column(db.String(500))  # 高亮后HTML文件的存储路径

    # 操作记录
    steps = db.Column(db.Text)  # JSON数组，每一步的操作和截图路径
    step_count = db.Column(db.Integer, default=0)  # 执行了多少步
    downloaded_files = db.Column(db.Text)  # JSON数组，下载的文件路径列表

    # 元数据
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    started_at = db.Column(db.DateTime)  # 任务开始执行时间
    completed_at = db.Column(db.DateTime)  # 任务完成时间
    error_message = db.Column(db.Text)  # 如果失败，记录错误信息

    # 通知和汇报
    is_read = db.Column(db.Boolean, default=False)  # 用户是否已"接听"
    briefing_prompt = db.Column(db.Text)  # 语音汇报时注入的提示词
    email_sent = db.Column(db.Boolean, default=False)  # 是否已发送邮件通知

    def to_dict(self):
        return {
            'id': self.id,
            'query': self.query,
            'target_url': self.target_url,
            'status': self.status,
            'summary': self.summary,
            'source_url': self.source_url,
            'step_count': self.step_count,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'is_read': self.is_read,
            'email_sent': self.email_sent,
            'error_message': self.error_message
        }
