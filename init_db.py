"""
初始化数据库 - 创建所有表
"""
import os
from dotenv import load_dotenv
from flask import Flask

# 加载环境变量
load_dotenv()

# 创建Flask应用
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///uniagent.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 导入db实例并初始化
from models import db
db.init_app(app)

# 导入模型（确保所有模型都被注册）
from models import User, Conversation, Message, ToolCall, Task

# 创建所有表
with app.app_context():
    db.create_all()
    print("✅ 数据库初始化成功！已创建所有表。")

    # 显示创建的表
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"\n已创建的表: {', '.join(tables)}")
