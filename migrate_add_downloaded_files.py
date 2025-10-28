"""
数据库迁移脚本 - 为 Task 表添加 downloaded_files 字段
"""
from flask import Flask
from models import db, Task
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 创建 Flask 应用
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///verifaible.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库
db.init_app(app)

def migrate():
    """执行迁移"""
    with app.app_context():
        # 检查数据库是否存在
        import sqlite3
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

        if not os.path.exists(db_path):
            print(f"❌ 数据库文件不存在: {db_path}")
            print("💡 请先运行应用创建数据库")
            return

        # 连接数据库并添加字段
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # 检查字段是否已存在
            cursor.execute("PRAGMA table_info(tasks)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'downloaded_files' in columns:
                print("✅ downloaded_files 字段已存在，无需迁移")
            else:
                # 添加新字段
                cursor.execute("ALTER TABLE tasks ADD COLUMN downloaded_files TEXT")
                conn.commit()
                print("✅ 成功添加 downloaded_files 字段")

        except Exception as e:
            print(f"❌ 迁移失败: {e}")
            conn.rollback()
        finally:
            conn.close()

if __name__ == '__main__':
    migrate()
