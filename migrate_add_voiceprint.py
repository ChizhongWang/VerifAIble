"""
数据库迁移脚本：添加声纹识别字段到 users 表
"""
import os
from dotenv import load_dotenv

load_dotenv()

from websocket_server import app
from models import db

def migrate_add_voiceprint_fields():
    """添加声纹识别相关字段到 users 表"""
    with app.app_context():
        # 获取数据库连接
        connection = db.engine.raw_connection()
        cursor = connection.cursor()

        try:
            # 检查数据库类型
            db_uri = app.config['SQLALCHEMY_DATABASE_URI']
            is_sqlite = db_uri.startswith('sqlite')

            print("正在添加声纹识别字段到 users 表...")

            # 要添加的字段
            fields_to_add = [
                ('voiceprint_profile', 'TEXT'),
                ('call_mode', 'VARCHAR(20)'),
                ('voiceprint_enabled', 'BOOLEAN DEFAULT 0' if is_sqlite else 'BOOLEAN DEFAULT FALSE'),
                ('voiceprint_enrolled_at', 'DATETIME')
            ]

            for field_name, field_type in fields_to_add:
                try:
                    # 检查字段是否已存在
                    if is_sqlite:
                        cursor.execute("PRAGMA table_info(users)")
                        existing_columns = [row[1] for row in cursor.fetchall()]
                    else:
                        cursor.execute("""
                            SELECT column_name FROM information_schema.columns
                            WHERE table_name='users' AND column_name=%s
                        """, (field_name,))
                        existing_columns = [row[0] for row in cursor.fetchall()]

                    if field_name not in existing_columns:
                        # 添加字段
                        alter_sql = f"ALTER TABLE users ADD COLUMN {field_name} {field_type}"
                        cursor.execute(alter_sql)
                        print(f"  ✓ 添加字段: {field_name}")
                    else:
                        print(f"  - 字段已存在，跳过: {field_name}")

                except Exception as e:
                    print(f"  ✗ 添加字段 {field_name} 失败: {e}")
                    continue

            connection.commit()
            print("\n✓ 数据库迁移完成！")
            print("\n新增字段:")
            print("  - voiceprint_profile: 声纹特征数据")
            print("  - call_mode: 通话模式（earpiece/speaker）")
            print("  - voiceprint_enabled: 是否启用声纹验证")
            print("  - voiceprint_enrolled_at: 声纹注册时间")

        except Exception as e:
            connection.rollback()
            print(f"\n✗ 迁移失败: {e}")
            raise

        finally:
            cursor.close()
            connection.close()

if __name__ == '__main__':
    migrate_add_voiceprint_fields()
