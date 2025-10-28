"""
邮件服务模块
使用 SMTP 发送任务完成通知邮件
"""
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailService:
    """邮件发送服务"""

    def __init__(self):
        """初始化邮件服务，从环境变量读取SMTP配置"""
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_user)
        self.from_name = os.getenv('FROM_NAME', 'VerifAIble')

        # 网站基础URL（用于生成跳转链接）
        self.base_url = os.getenv('BASE_URL', 'http://localhost:3001')

        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP配置不完整，邮件功能将不可用")

    def send_task_completion_email(
        self,
        to_emails: List[str],
        user_name: str,
        task: Dict,
        screenshots: List[str] = None
    ) -> bool:
        """
        发送任务完成通知邮件

        Args:
            to_emails: 收件人邮箱列表
            user_name: 用户名
            task: 任务字典（包含 query, summary, source_url, step_count, created_at 等）
            screenshots: 截图文件路径列表

        Returns:
            是否发送成功
        """
        try:
            # 创建邮件对象
            msg = MIMEMultipart('mixed')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = f"[VerifAIble] 您的查询任务已完成 - {task.get('query', '')[:30]}"

            # 生成"接听"链接
            callback_url = f"{self.base_url}/?task_id={task.get('id')}"

            # 创建HTML邮件正文
            html_body = self._generate_email_html(
                user_name=user_name,
                task=task,
                callback_url=callback_url
            )

            # 添加HTML正文
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            # 添加截图附件（如果有）
            if screenshots:
                for screenshot_path in screenshots[:5]:  # 最多附加5张截图
                    try:
                        self._attach_file(msg, screenshot_path)
                    except Exception as e:
                        logger.error(f"附加截图失败 {screenshot_path}: {e}")

            # 添加HTML报告附件（如果有）
            if task.get('report_html_path'):
                try:
                    self._attach_file(msg, task['report_html_path'])
                except Exception as e:
                    logger.error(f"附加HTML报告失败: {e}")

            # 发送邮件
            self._send_email(msg, to_emails)

            logger.info(f"任务完成邮件已发送到: {', '.join(to_emails)}")
            return True

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _generate_email_html(self, user_name: str, task: Dict, callback_url: str) -> str:
        """生成邮件HTML内容"""

        query = task.get('query', '')
        summary = task.get('summary', '')
        source_url = task.get('source_url', '')
        step_count = task.get('step_count', 0)
        created_at = task.get('created_at', '')

        # 格式化时间
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at).strftime('%Y-%m-%d %H:%M')
            except:
                pass

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo {{
            font-size: 28px;
            font-weight: bold;
            color: #10b981;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #666;
            font-size: 14px;
        }}
        .content {{
            margin: 25px 0;
        }}
        .section {{
            margin: 20px 0;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: #10b981;
            margin-bottom: 10px;
            border-left: 4px solid #10b981;
            padding-left: 10px;
        }}
        .query-box {{
            background-color: #f8f9fa;
            border-left: 4px solid #10b981;
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
            font-style: italic;
        }}
        .summary-box {{
            background-color: #f0fdf4;
            border: 1px solid #10b981;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }}
        .meta-info {{
            font-size: 13px;
            color: #666;
            margin: 10px 0;
        }}
        .meta-info strong {{
            color: #333;
        }}
        .cta-button {{
            display: inline-block;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            text-decoration: none;
            padding: 14px 32px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 20px 0;
            text-align: center;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
            transition: all 0.3s ease;
        }}
        .cta-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4);
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            color: #666;
            font-size: 13px;
        }}
        .attachments {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }}
        .attachments ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .attachments li {{
            margin: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">📞 VerifAIble</div>
            <div class="subtitle">您的智能语音助手</div>
        </div>

        <div class="content">
            <p>您好，<strong>{user_name}</strong>！</p>

            <p>您在 VerifAIble 中提出的问题已经完成深度研究。</p>

            <div class="section">
                <div class="section-title">📝 您的问题</div>
                <div class="query-box">
                    {query}
                </div>
            </div>

            <div class="section">
                <div class="section-title">💡 研究结果</div>
                <div class="summary-box">
                    {summary if summary else '正在处理中...'}
                </div>
            </div>

            <div class="section">
                <div class="section-title">📊 任务详情</div>
                <div class="meta-info">
                    <strong>信息来源:</strong> <a href="{source_url}" target="_blank">{source_url[:60]}...</a><br>
                    <strong>执行步骤:</strong> 共 {step_count} 步浏览器操作<br>
                    <strong>任务创建:</strong> {created_at}
                </div>
            </div>

            <div class="section">
                <div class="section-title">📎 附件说明</div>
                <div class="attachments">
                    <p>邮件附件包含：</p>
                    <ul>
                        <li>📸 浏览器操作截图（每一步的记录）</li>
                        <li>📄 高亮版网页（关键信息已标注）</li>
                    </ul>
                </div>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{callback_url}" class="cta-button">
                    🎧 点击接听语音汇报
                </a>
                <p style="font-size: 13px; color: #666; margin-top: 10px;">
                    AI 助手将为您详细讲解研究结果
                </p>
            </div>
        </div>

        <div class="footer">
            <p>本邮件由 VerifAIble 自动发送，请勿直接回复</p>
            <p style="margin-top: 10px;">
                <a href="{self.base_url}" style="color: #10b981;">访问 VerifAIble</a>
            </p>
        </div>
    </div>
</body>
</html>
        """

        return html

    def _attach_file(self, msg: MIMEMultipart, file_path: str):
        """添加附件到邮件"""
        from email.header import Header
        from email.utils import encode_rfc2231

        file_path = Path(file_path)

        if not file_path.exists():
            logger.warning(f"附件不存在: {file_path}")
            return

        # 获取文件名（需要正确编码中文）
        filename = file_path.name

        # 根据文件类型选择MIME类型
        if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']:
            # 图片附件
            with open(file_path, 'rb') as f:
                img = MIMEImage(f.read())
                # 使用RFC 2231编码文件名（支持中文）
                img.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', filename))
                msg.attach(img)
        elif file_path.suffix.lower() == '.pdf':
            # PDF附件（特别处理）
            with open(file_path, 'rb') as f:
                part = MIMEBase('application', 'pdf')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                # 使用RFC 2231编码文件名（支持中文）
                part.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', filename))
                msg.attach(part)
        else:
            # 其他文件（HTML、Markdown等）
            with open(file_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encoders.encode_base64(part)
                # 使用RFC 2231编码文件名（支持中文）
                part.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', filename))
                msg.attach(part)

    def _send_email(self, msg: MIMEMultipart, to_emails: List[str]):
        """发送邮件"""
        if not self.smtp_user or not self.smtp_password:
            raise Exception("SMTP配置不完整")

        # 连接SMTP服务器
        if self.smtp_port == 465:
            # SSL连接
            server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
        else:
            # TLS连接
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()

        # 登录
        server.login(self.smtp_user, self.smtp_password)

        # 发送
        server.send_message(msg)

        # 关闭连接
        server.quit()

        logger.info("邮件发送成功")

    def send_task_result_email(
        self,
        to_emails: List[str],
        user_name: str,
        task: Dict,
        attachments: List[str] = None
    ) -> bool:
        """
        发送任务结果邮件（支持PDF附件和下载文件）

        Args:
            to_emails: 收件人邮箱列表
            user_name: 用户名
            task: 任务字典（包含 query, summary, source_url, downloaded_files 等）
            attachments: 附件文件路径列表（包括下载的PDF、截图等）

        Returns:
            是否发送成功
        """
        try:
            # 创建邮件对象
            msg = MIMEMultipart('mixed')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(to_emails)
            msg['Subject'] = f"[VerifAIble] 您的查询任务已完成 - {task.get('query', '')[:30]}"

            # 生成"接听"链接
            callback_url = f"{self.base_url}/?task_id={task.get('id')}"

            # 创建HTML邮件正文（包含下载文件信息）
            html_body = self._generate_result_email_html(
                user_name=user_name,
                task=task,
                callback_url=callback_url,
                attachments=attachments or []
            )

            # 添加HTML正文
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            # 添加所有附件
            if attachments:
                for file_path in attachments:
                    try:
                        self._attach_file(msg, file_path)
                        logger.info(f"   📎 已附加文件: {Path(file_path).name}")
                    except Exception as e:
                        logger.error(f"附加文件失败 {file_path}: {e}")

            # 发送邮件
            self._send_email(msg, to_emails)

            logger.info(f"任务结果邮件已发送到: {', '.join(to_emails)}")
            return True

        except Exception as e:
            logger.error(f"发送邮件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _generate_result_email_html(
        self,
        user_name: str,
        task: Dict,
        callback_url: str,
        attachments: List[str]
    ) -> str:
        """生成任务结果邮件HTML内容（包含下载文件列表）"""

        query = task.get('query', '')
        summary = task.get('summary', '')
        source_url = task.get('source_url', '')
        step_count = task.get('step_count', 0)
        created_at = task.get('created_at', '')
        downloaded_files = task.get('downloaded_files', [])
        download_count = task.get('download_count', 0)

        # 格式化时间
        if isinstance(created_at, str):
            try:
                from datetime import datetime
                created_at = datetime.fromisoformat(created_at).strftime('%Y-%m-%d %H:%M')
            except:
                pass

        # 生成附件列表HTML
        attachments_html = ""
        if attachments:
            attachments_html = "<ul>"
            for file_path in attachments:
                file_name = Path(file_path).name
                file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
                file_size_kb = file_size / 1024

                # 判断文件类型
                file_ext = Path(file_path).suffix.lower()
                if file_ext == '.pdf':
                    icon = "📄"
                    file_type = "PDF文档"
                elif file_ext in ['.png', '.jpg', '.jpeg']:
                    icon = "📸"
                    file_type = "截图"
                elif file_ext in ['.html', '.htm']:
                    icon = "🌐"
                    file_type = "网页报告"
                elif file_ext == '.md':
                    icon = "📝"
                    file_type = "Markdown报告"
                else:
                    icon = "📎"
                    file_type = "文件"

                attachments_html += f"<li>{icon} <strong>{file_name}</strong> ({file_size_kb:.1f} KB) - {file_type}</li>"
            attachments_html += "</ul>"

        # 生成下载文件说明
        download_info_html = ""
        if download_count > 0:
            download_info_html = f"""
            <div class="section">
                <div class="section-title">📥 下载文件</div>
                <div class="meta-info">
                    本次任务共下载了 <strong>{download_count}</strong> 个文件，已作为附件随邮件发送。
                </div>
            </div>
            """

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .logo {{
            font-size: 28px;
            font-weight: bold;
            color: #10b981;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #666;
            font-size: 14px;
        }}
        .content {{
            margin: 25px 0;
        }}
        .section {{
            margin: 20px 0;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: #10b981;
            margin-bottom: 10px;
            border-left: 4px solid #10b981;
            padding-left: 10px;
        }}
        .query-box {{
            background-color: #f8f9fa;
            border-left: 4px solid #10b981;
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
            font-style: italic;
        }}
        .summary-box {{
            background-color: #f0fdf4;
            border: 1px solid #10b981;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }}
        .meta-info {{
            font-size: 13px;
            color: #666;
            margin: 10px 0;
        }}
        .meta-info strong {{
            color: #333;
        }}
        .meta-info a {{
            color: #10b981;
            text-decoration: none;
        }}
        .meta-info a:hover {{
            text-decoration: underline;
        }}
        .cta-button {{
            display: inline-block;
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            text-decoration: none;
            padding: 14px 32px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 20px 0;
            text-align: center;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
            transition: all 0.3s ease;
        }}
        .cta-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4);
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            color: #666;
            font-size: 13px;
        }}
        .attachments {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }}
        .attachments ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .attachments li {{
            margin: 8px 0;
            color: #333;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">📞 VerifAIble</div>
            <div class="subtitle">您的智能语音助手</div>
        </div>

        <div class="content">
            <p>您好，<strong>{user_name}</strong>！</p>

            <p>您在 VerifAIble 中提出的问题已经完成深度研究。</p>

            <div class="section">
                <div class="section-title">📝 您的问题</div>
                <div class="query-box">
                    {query}
                </div>
            </div>

            <div class="section">
                <div class="section-title">💡 研究结果</div>
                <div class="summary-box">
                    {summary if summary else '任务已完成，详细信息请查看附件。'}
                </div>
            </div>

            {download_info_html}

            <div class="section">
                <div class="section-title">📊 任务详情</div>
                <div class="meta-info">
                    <strong>信息来源:</strong> <a href="{source_url}" target="_blank">{source_url[:80]}{'...' if len(source_url) > 80 else ''}</a><br>
                    <strong>执行步骤:</strong> 共 {step_count} 步浏览器操作<br>
                    <strong>任务创建:</strong> {created_at}
                </div>
            </div>

            <div class="section">
                <div class="section-title">📎 邮件附件</div>
                <div class="attachments">
                    {attachments_html if attachments_html else '<p>本次任务没有附件</p>'}
                </div>
            </div>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{callback_url}" class="cta-button">
                    🎧 点击接听语音汇报
                </a>
                <p style="font-size: 13px; color: #666; margin-top: 10px;">
                    AI 助手将为您详细讲解研究结果
                </p>
            </div>
        </div>

        <div class="footer">
            <p>本邮件由 VerifAIble 自动发送，请勿直接回复</p>
            <p style="margin-top: 10px;">
                <a href="{self.base_url}" style="color: #10b981;">访问 VerifAIble</a>
            </p>
        </div>
    </div>
</body>
</html>
        """

        return html


# 测试函数
def test_email_service():
    """测试邮件服务"""
    service = EmailService()

    task = {
        'id': 123,
        'query': '国家对于预制菜的定义是什么',
        'summary': '根据国家相关部门发布的文件，预制菜是指以农、畜、禽、水产品为原料，配以各种辅料，经预加工（如分切、搅拌、腌制、成型、调味等）而成的成品或半成品。',
        'source_url': 'https://www.gov.cn/zhengce/content/202x-xx/xxxx.htm',
        'step_count': 5,
        'created_at': datetime.now().isoformat(),
        'report_html_path': 'task_data/reports/task_123_report.html'
    }

    # 测试发送（需要配置SMTP）
    to_email = os.getenv('TEST_EMAIL', 'test@example.com')

    success = service.send_task_completion_email(
        to_emails=[to_email],
        user_name='测试用户',
        task=task,
        screenshots=[]
    )

    if success:
        print("✅ 测试邮件发送成功")
    else:
        print("❌ 测试邮件发送失败")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    test_email_service()
