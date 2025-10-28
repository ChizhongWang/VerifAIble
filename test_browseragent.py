"""
测试浏览器代理 - 专注于下载公告PDF并发送邮件
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from browser_agent import BrowserAgent
from email_agent import EmailAgent

# 加载环境变量
load_dotenv()

# 启用详细日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_browseragent_headed():
    """有头模式测试 - 可以观察操作过程"""
    print("\n" + "=" * 70)
    print("有头模式测试 - 观察浏览器操作")
    print("=" * 70)
    print("提示: 浏览器窗口将打开，你可以看到AI的每一步操作")
    print("每个操作会延迟1秒，便于观察")
    print("-" * 70)

    api_key = os.getenv('OPENAI_API_KEY')
    agent = BrowserAgent(
        api_key=api_key,
        max_steps=10,
        headless=False,  # 显示浏览器
        slow_mo=1000     # 每个操作延迟1秒
    )

    # 步骤1: 执行浏览器任务（下载PDF）
    result = await agent.execute_task(
        query='你位于深交所"上市公司公告"的检索页面，找到并下载安克创新最新的1条公告的PDF文件到本地，并且发送到我的邮箱里',
        target_url="https://www.szse.cn/disclosure/listed/notice/index.html",
        task_id=6002
    )

    print("\n" + "=" * 70)
    print("浏览器任务完成!")
    print(f"成功: {result['success']}")
    print(f"总步数: {len(result['steps'])}")
    print(f"下载文件: {result.get('download_count', 0)} 个")

    # 步骤2: 如果任务成功，发送邮件
    # 检查是否有下载的文件（包括本次下载和之前已存在的）
    download_dir = os.path.join(os.getcwd(), 'downloads')
    has_files = os.path.exists(download_dir) and len([f for f in os.listdir(download_dir) if f.endswith('.pdf')]) > 0

    if result['success'] and has_files:
        print("\n" + "-" * 70)
        print("开始发送邮件...")
        print("-" * 70)

        # 获取收件人邮箱（从环境变量或使用测试邮箱）
        recipient_email = os.getenv('RECIPIENT_EMAIL', os.getenv('TEST_EMAIL'))

        if not recipient_email:
            print("⚠️  未设置收件人邮箱，跳过邮件发送")
            print("   提示: 设置 RECIPIENT_EMAIL 或 TEST_EMAIL 环境变量以启用邮件发送")
        else:
            # 如果本次没有下载新文件，但downloads目录有文件，更新download_count和downloaded_files
            if result.get('download_count', 0) == 0:
                pdf_files = [f for f in os.listdir(download_dir) if f.endswith('.pdf')]
                # 按修改时间排序，获取最新的文件
                pdf_files_full_path = [os.path.join(download_dir, f) for f in pdf_files]
                pdf_files_full_path.sort(key=lambda x: os.path.getmtime(x), reverse=True)

                result['download_count'] = len(pdf_files_full_path)
                result['downloaded_files'] = pdf_files_full_path  # 添加文件路径列表
                print(f"📁 检测到 downloads 目录中有 {len(pdf_files)} 个PDF文件")

            # 补充任务信息
            result['task_id'] = 6002
            result['query'] = "找到并下载安克创新最新的1条公告PDF文件到本地"
            result['created_at'] = agent.start_time if hasattr(agent, 'start_time') else ''

            # 从环境变量获取用户名（后续可以从数据库读取）
            user_name = os.getenv('USER_NAME', '用户')

            # 创建邮件代理并发送
            email_agent = EmailAgent()
            email_success = email_agent.send_task_result(
                task_result=result,
                recipient_email=recipient_email,
                user_name=user_name,
                include_downloads=True,
                include_screenshots=False  # 测试时不附加截图
            )

            if email_success:
                print(f"✅ 邮件发送成功到: {recipient_email}")
            else:
                print(f"❌ 邮件发送失败")
    else:
        print("\n⚠️  任务未成功或 downloads 目录中没有PDF文件，跳过邮件发送")

    print("\n" + "=" * 70)
    print("所有测试完成!")
    print("=" * 70)

async def main():
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ 请设置 OPENAI_API_KEY 环境变量")
        return

    await test_browseragent_headed()

if __name__ == '__main__':
    asyncio.run(main())
