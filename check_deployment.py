"""
部署检查脚本 - 验证所有配置和依赖是否就绪
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def check_env_variables():
    """检查环境变量"""
    print("\n" + "=" * 70)
    print("1. 检查环境变量")
    print("=" * 70)

    required_vars = [
        'OPENAI_API_KEY',
        'SMTP_HOST',
        'SMTP_PORT',
        'SMTP_USER',
        'SMTP_PASSWORD',
        'FROM_EMAIL',
        'RECIPIENT_EMAIL'
    ]

    all_ok = True
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # 隐藏敏感信息
            if 'KEY' in var or 'PASSWORD' in var:
                display_value = value[:10] + '...' if len(value) > 10 else '***'
            else:
                display_value = value
            print(f"  ✓ {var}: {display_value}")
        else:
            print(f"  ✗ {var}: 未配置")
            all_ok = False

    return all_ok


def check_dependencies():
    """检查Python依赖"""
    print("\n" + "=" * 70)
    print("2. 检查Python依赖")
    print("=" * 70)

    packages_to_check = [
        ('flask', 'flask'),
        ('flask-cors', 'flask_cors'),
        ('flask-sqlalchemy', 'flask_sqlalchemy'),
        ('playwright', 'playwright'),
        ('openai', 'openai'),
        ('python-dotenv', 'dotenv')
    ]

    all_ok = True
    for package_name, import_name in packages_to_check:
        try:
            __import__(import_name)
            print(f"  ✓ {package_name}")
        except ImportError:
            print(f"  ✗ {package_name}: 未安装")
            all_ok = False

    return all_ok


def check_playwright():
    """检查Playwright浏览器"""
    print("\n" + "=" * 70)
    print("3. 检查Playwright浏览器")
    print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("  ✓ Chromium 浏览器已安装且可正常运行")
        return True
    except Exception as e:
        print(f"  ✗ Chromium 浏览器检查失败: {e}")
        print("  💡 运行: playwright install chromium")
        return False


def check_directories():
    """检查必要的目录"""
    print("\n" + "=" * 70)
    print("4. 检查目录结构")
    print("=" * 70)

    required_dirs = [
        'downloads',
        'task_data',
        'task_data/reports',
        'static'
    ]

    all_ok = True
    for dir_path in required_dirs:
        full_path = os.path.join(os.getcwd(), dir_path)
        if os.path.exists(full_path):
            print(f"  ✓ {dir_path}/")
        else:
            print(f"  ✗ {dir_path}/: 不存在")
            try:
                os.makedirs(full_path)
                print(f"    ✓ 已自动创建")
            except Exception as e:
                print(f"    ✗ 创建失败: {e}")
                all_ok = False

    return all_ok


def check_files():
    """检查必要的文件"""
    print("\n" + "=" * 70)
    print("5. 检查必要文件")
    print("=" * 70)

    required_files = [
        'websocket_server.py',
        'browser_agent.py',
        'email_agent.py',
        'email_service.py',
        'models.py',
        'init_db.py',
        'requirements.txt',
        '.env'
    ]

    all_ok = True
    for file_path in required_files:
        full_path = os.path.join(os.getcwd(), file_path)
        if os.path.exists(full_path):
            size_kb = os.path.getsize(full_path) / 1024
            print(f"  ✓ {file_path} ({size_kb:.1f} KB)")
        else:
            print(f"  ✗ {file_path}: 不存在")
            all_ok = False

    return all_ok


def check_database():
    """检查数据库"""
    print("\n" + "=" * 70)
    print("6. 检查数据库")
    print("=" * 70)

    db_url = os.getenv('DATABASE_URL', 'sqlite:///verifaible.db')
    db_path = db_url.replace('sqlite:///', '')

    if os.path.exists(db_path):
        size_kb = os.path.getsize(db_path) / 1024
        print(f"  ✓ 数据库文件存在: {db_path} ({size_kb:.1f} KB)")

        # 检查表结构
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # 检查Task表是否有downloaded_files字段
            cursor.execute("PRAGMA table_info(tasks)")
            columns = [col[1] for col in cursor.fetchall()]

            if 'downloaded_files' in columns:
                print("  ✓ Task表包含 downloaded_files 字段")
            else:
                print("  ⚠️  Task表缺少 downloaded_files 字段")
                print("    💡 运行: python migrate_add_downloaded_files.py")

            conn.close()
            return True
        except Exception as e:
            print(f"  ✗ 数据库检查失败: {e}")
            return False
    else:
        print(f"  ⚠️  数据库文件不存在: {db_path}")
        print("    💡 首次运行服务器时会自动创建")
        return True


def check_smtp_connection():
    """检查SMTP连接"""
    print("\n" + "=" * 70)
    print("7. 检查SMTP邮件服务")
    print("=" * 70)

    try:
        import smtplib
        from email.mime.text import MIMEText

        smtp_host = os.getenv('SMTP_HOST')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')

        if not all([smtp_host, smtp_port, smtp_user, smtp_password]):
            print("  ⚠️  SMTP配置不完整")
            return False

        # 尝试连接
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.quit()

        print(f"  ✓ SMTP连接成功: {smtp_host}:{smtp_port}")
        return True

    except Exception as e:
        print(f"  ✗ SMTP连接失败: {e}")
        print("  💡 检查SMTP配置和网络连接")
        return False


def check_openai_api():
    """检查OpenAI API"""
    print("\n" + "=" * 70)
    print("8. 检查OpenAI API")
    print("=" * 70)

    try:
        from openai import OpenAI

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("  ✗ OPENAI_API_KEY 未配置")
            return False

        client = OpenAI(api_key=api_key)

        # 简单测试API连接
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5
        )

        print("  ✓ OpenAI API 连接成功")
        return True

    except Exception as e:
        print(f"  ✗ OpenAI API 连接失败: {e}")
        print("  💡 检查API密钥是否有效")
        return False


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("VerifAIble 部署检查工具")
    print("=" * 70)

    checks = [
        ("环境变量", check_env_variables),
        ("Python依赖", check_dependencies),
        ("Playwright浏览器", check_playwright),
        ("目录结构", check_directories),
        ("必要文件", check_files),
        ("数据库", check_database),
        ("SMTP邮件", check_smtp_connection),
        ("OpenAI API", check_openai_api)
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n  ❌ {name} 检查出错: {e}")
            results[name] = False

    # 汇总结果
    print("\n" + "=" * 70)
    print("检查结果汇总")
    print("=" * 70)

    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ 所有检查通过！可以启动服务器")
        print("\n运行以下命令启动服务器:")
        print("  python websocket_server.py")
    else:
        print("⚠️  部分检查未通过，请修复上述问题后再启动服务器")
        sys.exit(1)
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
