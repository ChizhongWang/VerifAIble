"""
直接测试邮件发送功能（使用已有的PDF文件）
"""
import os
import logging
from email_agent import EmailAgent
from datetime import datetime

# 加载.env文件
from pathlib import Path
env_file = Path('.env')
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# 启用详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_email_send():
    """直接测试邮件发送"""
    print("\n" + "=" * 70)
    print("邮件发送测试")
    print("=" * 70)

    # 检查PDF文件是否存在
    pdf_file = "downloads/安克创新：关于使用部分暂时闲置募集资金进行现金管理的进展公告.pdf"

    if not os.path.exists(pdf_file):
        print(f"❌ PDF文件不存在: {pdf_file}")
        print("   请先运行 browser_agent 下载文件")
        return

    print(f"✅ 找到PDF文件: {pdf_file}")
    file_size = os.path.getsize(pdf_file) / 1024
    print(f"   文件大小: {file_size:.1f} KB")

    # 构造任务结果（模拟browser_agent的返回）
    task_result = {
        'task_id': 6002,
        'success': True,
        'query': '找到并下载安克创新最新的1条公告PDF文件到本地',
        'summary': '已成功下载安克创新（股票代码300866）最新公告：《关于使用部分暂时闲置募集资金进行现金管理的进展公告》',
        'source_url': 'https://www.szse.cn/disclosure/listed/bulletinDetail/index.html?beefc1b9-d2aa-4218-99ae-3bc133673db6',
        'downloaded_files': [pdf_file],
        'download_count': 1,
        'steps': [],
        'created_at': datetime.now().isoformat(),
    }

    # 获取收件人邮箱
    recipient_email = os.getenv('RECIPIENT_EMAIL')

    if not recipient_email:
        print("❌ 未设置收件人邮箱")
        print("   请在 .env 文件中设置 RECIPIENT_EMAIL")
        return

    print(f"\n📧 收件人: {recipient_email}")
    print("\n" + "-" * 70)
    print("开始发送邮件...")
    print("-" * 70)

    # 创建邮件代理并发送
    email_agent = EmailAgent()
    success = email_agent.send_task_result(
        task_result=task_result,
        recipient_email=recipient_email,
        user_name="测试用户",
        include_downloads=True,
        include_screenshots=False  # 不附加截图
    )

    print("\n" + "=" * 70)
    if success:
        print("✅ 邮件发送成功！")
        print(f"   请检查邮箱: {recipient_email}")
        print("\n邮件内容包括：")
        print("  📝 任务查询和结果")
        print("  🔗 文件来源链接（可点击）")
        print("  📄 PDF附件（安克创新公告）")
        print("  📊 附件详细信息")
    else:
        print("❌ 邮件发送失败")
        print("   请检查SMTP配置和网络连接")
    print("=" * 70)

if __name__ == '__main__':
    test_email_send()
