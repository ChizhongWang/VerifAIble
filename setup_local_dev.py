#!/usr/bin/env python
"""
本地开发环境快速配置脚本
自动生成必要的密钥和配置

使用方法:
  python setup_local_dev.py           # 交互模式
  python setup_local_dev.py --yes     # 自动模式（所有提示自动确认）
  python setup_local_dev.py -y        # 同上
"""
import os
from cryptography.fernet import Fernet
import secrets

def generate_keys(auto_yes=False):
    """生成所有必要的密钥"""
    print("\n" + "=" * 70)
    print("VerifAIble 本地开发环境配置")
    print("=" * 70)

    # 生成加密密钥
    encryption_key = Fernet.generate_key().decode()
    print(f"\n✅ ENCRYPTION_KEY (用于加密用户 API 密钥):")
    print(f"   {encryption_key}")

    # 生成 Flask Secret Key
    secret_key = secrets.token_hex(24)
    print(f"\n✅ SECRET_KEY (Flask session 密钥):")
    print(f"   {secret_key}")

    # 检查现有 .env 文件
    env_path = '.env'
    if os.path.exists(env_path):
        print(f"\n⚠️  .env 文件已存在")
        if auto_yes:
            choice = 'y'
            print("自动模式：将备份并更新")
        else:
            try:
                choice = input("是否备份并更新？(y/n): ").lower()
            except (EOFError, KeyboardInterrupt):
                print("\n检测到非交互模式，自动备份并更新")
                choice = 'y'

        if choice != 'y':
            print("\n已取消。请手动复制上述密钥到 .env 文件。")
            print("\n你也可以使用 --yes 参数自动确认所有操作:")
            print("  python setup_local_dev.py --yes")
            return

        # 备份现有文件
        import shutil
        backup_path = f'.env.backup.{secrets.token_hex(4)}'
        shutil.copy(env_path, backup_path)
        print(f"✅ 已备份到: {backup_path}")

    # 读取 .env.example 或创建新的
    if os.path.exists('.env.example'):
        with open('.env.example', 'r', encoding='utf-8') as f:
            env_content = f.read()
    else:
        env_content = """# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# 数据库（本地开发使用 SQLite）
DATABASE_URL=sqlite:///verifaible.db

# Google OAuth（本地开发）
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# 加密密钥（用于加密存储用户的 API 密钥）
ENCRYPTION_KEY=GENERATED_KEY_HERE

# Flask 配置
SECRET_KEY=GENERATED_KEY_HERE
HTTPS=False  # 本地开发使用 HTTP
DEBUG=True   # 开发模式

# SMTP 邮件配置
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your_email@qq.com
SMTP_PASSWORD=your_smtp_auth_code
FROM_EMAIL=your_email@qq.com
FROM_NAME=VerifAIble

# 收件人邮箱（测试用）
RECIPIENT_EMAIL=your_email@qq.com
USER_NAME=开发者
"""

    # 更新密钥
    env_content = env_content.replace('ENCRYPTION_KEY=GENERATED_KEY_HERE', f'ENCRYPTION_KEY={encryption_key}')
    env_content = env_content.replace('SECRET_KEY=GENERATED_KEY_HERE', f'SECRET_KEY={secret_key}')

    # 写入文件
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(env_content)

    print(f"\n✅ .env 文件已更新")

    # 显示需要手动配置的项
    print("\n" + "=" * 70)
    print("⚠️  请手动配置以下项:")
    print("=" * 70)

    needs_config = [
        ("OPENAI_API_KEY", "OpenAI API 密钥", "https://platform.openai.com/api-keys"),
        ("GOOGLE_CLIENT_ID", "Google OAuth 客户端 ID", "https://console.cloud.google.com/"),
        ("GOOGLE_CLIENT_SECRET", "Google OAuth 客户端密钥", "https://console.cloud.google.com/"),
        ("SMTP_USER", "SMTP 用户名（邮箱地址）", None),
        ("SMTP_PASSWORD", "SMTP 授权码（不是邮箱密码！）", "QQ邮箱: 设置→账户→POP3/IMAP/SMTP"),
        ("FROM_EMAIL", "发件人邮箱", None),
        ("RECIPIENT_EMAIL", "收件人邮箱（测试用）", None),
    ]

    for key, description, url in needs_config:
        print(f"\n{key}:")
        print(f"  说明: {description}")
        if url:
            print(f"  获取地址: {url}")


def check_dependencies():
    """检查依赖是否安装"""
    print("\n" + "=" * 70)
    print("检查依赖")
    print("=" * 70)

    required_packages = [
        'flask',
        'flask_cors',
        'flask_sqlalchemy',
        'authlib',
        'cryptography',
        'playwright',
        'openai',
        'python-dotenv',
        'requests'
    ]

    missing = []
    for package in required_packages:
        try:
            package_import = package.replace('-', '_')
            __import__(package_import)
            print(f"✓ {package}")
        except ImportError:
            print(f"✗ {package} - 未安装")
            missing.append(package)

    if missing:
        print(f"\n⚠️  缺少 {len(missing)} 个依赖包")
        print("\n运行以下命令安装:")
        print(f"  pip install {' '.join(missing)}")
        return False
    else:
        print("\n✅ 所有依赖已安装")
        return True


def setup_database(auto_yes=False):
    """初始化数据库"""
    print("\n" + "=" * 70)
    print("数据库设置")
    print("=" * 70)

    db_path = 'verifaible.db'

    if os.path.exists(db_path):
        print(f"⚠️  数据库已存在: {db_path}")
        if auto_yes:
            choice = 'y'
            print("自动模式：将重新创建数据库")
        else:
            try:
                choice = input("是否重新创建？(y/n): ").lower()
            except (EOFError, KeyboardInterrupt):
                print("\n检测到非交互模式，跳过数据库初始化")
                return

        if choice != 'y':
            print("跳过数据库初始化")
            return

        os.remove(db_path)
        print("✅ 已删除旧数据库")

    print("\n初始化数据库...")
    os.system('python init_db.py')

    print("\n运行数据库迁移...")
    os.system('python migrate_add_downloaded_files.py')

    print("\n✅ 数据库设置完成")


def check_playwright():
    """检查 Playwright 浏览器"""
    print("\n" + "=" * 70)
    print("检查 Playwright 浏览器")
    print("=" * 70)

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("✅ Chromium 浏览器已安装")
        return True
    except Exception as e:
        print(f"✗ Chromium 浏览器未安装或无法启动")
        print(f"  错误: {e}")
        print("\n运行以下命令安装:")
        print("  playwright install chromium")
        return False


def show_next_steps():
    """显示后续步骤"""
    print("\n" + "=" * 70)
    print("🎉 配置完成！后续步骤:")
    print("=" * 70)

    steps = [
        ("1. 配置 Google OAuth", [
            "访问: https://console.cloud.google.com/",
            "创建 OAuth 2.0 凭据",
            "添加重定向 URI: http://localhost:3001/auth/callback",
            "复制客户端 ID 和密钥到 .env 文件"
        ]),
        ("2. 编辑 .env 文件", [
            "填入 OPENAI_API_KEY",
            "填入 GOOGLE_CLIENT_ID 和 GOOGLE_CLIENT_SECRET",
            "配置 SMTP 邮件设置",
        ]),
        ("3. 启动服务器", [
            "python websocket_server.py",
            "访问: http://localhost:3001"
        ]),
        ("4. 测试功能", [
            "登录测试: 访问 http://localhost:3001 并用 Google 登录",
            "API 测试: python test_email_only.py",
            "集成测试: python test_server_integration.py"
        ])
    ]

    for title, items in steps:
        print(f"\n{title}:")
        for item in items:
            print(f"  • {item}")

    print("\n📚 详细文档:")
    print("  • LOCAL_DEVELOPMENT_SETUP.md - 完整配置指南")
    print("  • LOCAL_TEST_GUIDE.md - 测试指南")
    print("  • QUICK_START.md - 快速开始")


def main():
    """主函数"""
    import sys

    # 检查命令行参数
    auto_yes = '--yes' in sys.argv or '-y' in sys.argv

    print("\n" + "=" * 70)
    print("🚀 VerifAIble 本地开发环境配置向导")
    print("=" * 70)

    if auto_yes:
        print("✅ 自动模式已启用（--yes）")

    # 1. 生成密钥
    generate_keys(auto_yes)

    # 2. 检查依赖
    deps_ok = check_dependencies()

    # 3. 检查 Playwright
    playwright_ok = check_playwright()

    # 4. 设置数据库
    if auto_yes:
        setup_database(auto_yes)
    else:
        print()
        try:
            choice = input("\n是否初始化数据库？(y/n): ").lower()
            if choice == 'y':
                setup_database(auto_yes)
        except (EOFError, KeyboardInterrupt):
            print("\n检测到非交互模式，跳过数据库初始化")

    # 5. 显示后续步骤
    show_next_steps()

    print("\n" + "=" * 70)
    if deps_ok and playwright_ok:
        print("✅ 环境配置完成！")
        print("按照上述步骤完成 Google OAuth 配置后即可开始开发")
    else:
        print("⚠️  请先安装缺失的依赖")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
