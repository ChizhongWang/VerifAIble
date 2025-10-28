"""
测试服务器集成 - 验证 BrowserAgent + EmailAgent 在服务器中的工作流程
"""
import asyncio
import os
from dotenv import load_dotenv
from browser_agent import BrowserAgent
from email_agent import EmailAgent
import json

# 加载环境变量
load_dotenv()


async def test_full_workflow():
    """测试完整工作流程：BrowserAgent执行 → EmailAgent发送"""

    print("\n" + "=" * 70)
    print("测试完整工作流程")
    print("=" * 70)

    # 模拟服务器场景
    task_id = 9999  # 测试任务ID
    query = "找到并下载安克创新最新的1条公告PDF文件"
    target_url = "https://www.szse.cn/disclosure/listed/notice/index.html"
    user_id = 1
    user_name = os.getenv('USER_NAME', '测试用户')
    recipient_email = os.getenv('RECIPIENT_EMAIL')

    if not recipient_email:
        print("❌ 未配置 RECIPIENT_EMAIL 环境变量")
        return

    print(f"📋 任务ID: {task_id}")
    print(f"🔍 查询: {query}")
    print(f"🌐 目标URL: {target_url}")
    print(f"👤 用户: {user_name} ({recipient_email})")
    print("-" * 70)

    # 步骤1: 执行浏览器任务
    print("\n【步骤1】执行 BrowserAgent 任务...")
    api_key = os.getenv('OPENAI_API_KEY')
    agent = BrowserAgent(
        api_key=api_key,
        max_steps=10,
        headless=True  # 服务器模式使用无头浏览器
    )

    result = await agent.execute_task(
        query=query,
        target_url=target_url,
        task_id=task_id
    )

    print(f"\n✅ 任务完成: {result['success']}")
    print(f"📊 执行步骤: {len(result.get('steps', []))}")
    print(f"📥 下载文件: {result.get('download_count', 0)} 个")

    if result.get('downloaded_files'):
        print("\n下载的文件:")
        for file_path in result['downloaded_files']:
            if os.path.exists(file_path):
                size_kb = os.path.getsize(file_path) / 1024
                print(f"  ✓ {os.path.basename(file_path)} ({size_kb:.1f} KB)")

    # 如果没有下载新文件，检查downloads目录
    if result.get('download_count', 0) == 0:
        download_dir = os.path.join(os.getcwd(), 'downloads')
        if os.path.exists(download_dir):
            pdf_files = [f for f in os.listdir(download_dir) if f.endswith('.pdf')]
            if pdf_files:
                pdf_files_full = [os.path.join(download_dir, f) for f in pdf_files]
                pdf_files_full.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                result['downloaded_files'] = pdf_files_full
                result['download_count'] = len(pdf_files_full)
                print(f"\n💡 检测到 downloads 目录中有 {len(pdf_files)} 个PDF文件")

    # 步骤2: 发送邮件
    if result['success'] and result.get('download_count', 0) > 0:
        print("\n" + "-" * 70)
        print("【步骤2】发送邮件通知...")
        print("-" * 70)

        # 补充任务信息
        result['task_id'] = task_id
        result['query'] = query
        result['created_at'] = agent.start_time if hasattr(agent, 'start_time') else ''

        # 创建邮件代理并发送
        email_agent = EmailAgent()
        email_success = email_agent.send_task_result(
            task_result=result,
            recipient_email=recipient_email,
            user_name=user_name,
            include_downloads=True,
            include_screenshots=True  # 测试时附加截图
        )

        if email_success:
            print(f"\n✅ 邮件发送成功到: {recipient_email}")
        else:
            print(f"\n❌ 邮件发送失败")
    else:
        print("\n⚠️  任务未成功或没有下载文件，跳过邮件发送")

    # 步骤3: 显示任务摘要（模拟数据库保存）
    print("\n" + "=" * 70)
    print("任务摘要（将保存到数据库）")
    print("=" * 70)
    print(f"task_id: {task_id}")
    print(f"query: {query}")
    print(f"status: {'completed' if result['success'] else 'failed'}")
    print(f"summary: {result.get('summary', 'N/A')[:100]}...")
    print(f"source_url: {result.get('source_url', 'N/A')}")
    print(f"step_count: {len(result.get('steps', []))}")
    print(f"downloaded_files: {json.dumps(result.get('downloaded_files', []), ensure_ascii=False)[:100]}...")
    print(f"task_report_path: {result.get('task_report_path', 'N/A')}")
    print(f"email_sent: {email_success if 'email_success' in locals() else False}")

    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)


async def main():
    """主函数"""
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ 请设置 OPENAI_API_KEY 环境变量")
        return

    if not os.getenv('RECIPIENT_EMAIL'):
        print("❌ 请设置 RECIPIENT_EMAIL 环境变量")
        return

    await test_full_workflow()


if __name__ == '__main__':
    asyncio.run(main())
