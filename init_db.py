"""
数据库初始化脚本
"""
import os
from dotenv import load_dotenv

load_dotenv()

from websocket_server import app
from models import db

def init_database():
    """初始化数据库"""
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("✓ 数据库表已创建")

        # 显示表信息
        print("\n创建的数据库表:")
        print("- users (用户表)")
        print("- conversations (对话记录表)")
        print("- messages (消息表)")
        print("- tool_calls (工具调用表)")

        # 显示数据库路径
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('sqlite'):
            db_path = db_uri.replace('sqlite:///', '')
            print(f"\nSQLite数据库位置: {os.path.abspath(db_path)}")
        else:
            print(f"\n数据库URI: {db_uri}")

if __name__ == '__main__':
    init_database()
