"""
邮件代理 - 处理任务完成后的邮件发送
负责将浏览器任务结果通过邮件发送给用户
"""
import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
from email_service import EmailService

logger = logging.getLogger(__name__)


class EmailAgent:
    """邮件代理 - 负责发送任务完成邮件"""

    def __init__(self):
        """初始化邮件代理"""
        self.email_service = EmailService()
        logger.info("📧 邮件代理已初始化")

    def send_task_result(
        self,
        task_result: Dict,
        recipient_email: str,
        user_name: str = "用户",
        include_downloads: bool = True,
        include_screenshots: bool = True
    ) -> bool:
        """
        发送任务完成邮件

        Args:
            task_result: browser_agent返回的任务结果字典
            recipient_email: 收件人邮箱
            user_name: 用户名
            include_downloads: 是否附加下载的文件
            include_screenshots: 是否附加截图

        Returns:
            是否发送成功
        """
        try:
            logger.info(f"📧 开始发送任务结果邮件到: {recipient_email}")

            # 提取任务信息
            task_info = {
                'id': task_result.get('task_id', 'unknown'),
                'query': task_result.get('query', ''),
                'summary': task_result.get('summary', ''),
                'source_url': task_result.get('source_url', ''),
                'step_count': len(task_result.get('steps', [])),
                'created_at': task_result.get('created_at', ''),
                'downloaded_files': task_result.get('downloaded_files', []),
                'download_count': task_result.get('download_count', 0)
            }

            # 准备附件列表
            attachments = []

            # 1. 添加下载的文件（PDF等）
            if include_downloads and task_result.get('downloaded_files'):
                for file_path in task_result['downloaded_files']:
                    if os.path.exists(file_path):
                        attachments.append(file_path)
                        logger.info(f"   📎 附加下载文件: {os.path.basename(file_path)}")

            # 2. 添加截图（可选，最多5张）
            if include_screenshots and task_result.get('steps'):
                screenshot_count = 0
                for step in task_result['steps']:
                    if screenshot_count >= 5:
                        break
                    screenshot_path = step.get('screenshot')
                    if screenshot_path and os.path.exists(screenshot_path):
                        attachments.append(screenshot_path)
                        screenshot_count += 1

            # 3. 添加任务报告（如果有）
            if task_result.get('task_report_path'):
                report_path = task_result['task_report_path']
                if os.path.exists(report_path):
                    attachments.append(report_path)
                    logger.info(f"   📎 附加任务报告: {os.path.basename(report_path)}")

            # 发送邮件
            success = self.email_service.send_task_result_email(
                to_emails=[recipient_email],
                user_name=user_name,
                task=task_info,
                attachments=attachments
            )

            if success:
                logger.info(f"✅ 邮件发送成功到: {recipient_email}")
            else:
                logger.error(f"❌ 邮件发送失败到: {recipient_email}")

            return success

        except Exception as e:
            logger.error(f"❌ 邮件代理发送失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def format_email_body(self, task_result: Dict) -> str:
        """
        格式化邮件正文（用于预览）

        Args:
            task_result: 任务结果

        Returns:
            格式化后的邮件正文文本
        """
        query = task_result.get('query', '')
        summary = task_result.get('summary', '')
        source_url = task_result.get('source_url', '')
        downloaded_files = task_result.get('downloaded_files', [])

        body = f"""
任务查询: {query}

研究结果:
{summary}

信息来源: {source_url}

下载文件:
"""
        for file_path in downloaded_files:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            body += f"  - {file_name} ({file_size / 1024:.1f} KB)\n"

        return body


# 测试函数
async def test_email_agent():
    """测试邮件代理"""
    agent = EmailAgent()

    # 模拟browser_agent的返回结果
    task_result = {
        'task_id': 6002,
        'query': '找到并下载300866股票最新的1条公告PDF',
        'summary': '已成功下载安克创新（股票代码300866）最新公告：《关于使用部分暂时闲置募集资金进行现金管理的进展公告》',
        'source_url': 'https://www.szse.cn/disclosure/listed/bulletinDetail/index.html?xxx',
        'steps': [],
        'downloaded_files': [
            'downloads/安克创新：关于使用部分暂时闲置募集资金进行现金管理的进展公告.pdf'
        ],
        'download_count': 1,
        'created_at': '2025-10-28 10:00:00',
        'task_report_path': 'task_data/reports/task_6002_report.md'
    }

    # 从环境变量获取测试邮箱
    test_email = os.getenv('TEST_EMAIL', 'test@example.com')

    # 发送邮件
    success = agent.send_task_result(
        task_result=task_result,
        recipient_email=test_email,
        user_name='测试用户',
        include_downloads=True,
        include_screenshots=False  # 测试时不附加截图
    )

    if success:
        print("✅ 邮件代理测试成功")
    else:
        print("❌ 邮件代理测试失败")


if __name__ == '__main__':
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_email_agent())
