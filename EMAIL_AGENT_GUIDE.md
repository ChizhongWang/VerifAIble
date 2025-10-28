# Email Agent 使用指南

## 功能概述

Email Agent 是一个独立的邮件发送代理，负责将 Browser Agent 的任务结果通过邮件发送给用户。

### 核心功能

1. **发送任务完成邮件**
   - 包含任务查询、研究结果、信息来源
   - 精美的HTML邮件模板
   - 支持附加PDF、截图等文件

2. **智能附件管理**
   - 自动附加下载的PDF文件
   - 可选附加任务截图（最多5张）
   - 支持任务报告附件

3. **邮件内容增强**
   - 显示文件来源链接（可点击）
   - 列出所有附件详情（文件名、大小、类型）
   - 下载文件数量统计

---

## 架构设计

### 职责分离

```
Browser Agent (下载) → Email Agent (发送邮件)
     ↓
  任务结果字典
     ↓
  Email Service (SMTP发送)
```

**设计理念**:
- Browser Agent 专注于浏览器自动化和文件下载
- Email Agent 专注于邮件内容组织和发送
- Email Service 提供底层SMTP邮件发送能力

### 数据流

```python
# 1. Browser Agent 完成任务
task_result = {
    'success': True,
    'query': '...',
    'summary': '...',
    'source_url': 'https://...',
    'downloaded_files': ['file1.pdf', 'file2.pdf'],
    'download_count': 2,
    'steps': [...]
}

# 2. Email Agent 发送邮件
email_agent = EmailAgent()
email_agent.send_task_result(
    task_result=task_result,
    recipient_email='user@example.com',
    user_name='用户名',
    include_downloads=True
)
```

---

## 快速开始

### 1. 环境配置

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# OpenAI API
OPENAI_API_KEY=sk-xxx

# 邮件服务（Gmail示例）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password    # 不是邮箱密码！需要生成应用专用密码
FROM_EMAIL=your_email@gmail.com
FROM_NAME=VerifAIble

# 收件人
RECIPIENT_EMAIL=recipient@example.com
```

#### Gmail 应用专用密码生成步骤

1. 访问 Google 账户设置: https://myaccount.google.com/
2. 导航到 "安全性" → "两步验证"（必须先启用）
3. 在"两步验证"页面，找到"应用专用密码"
4. 选择"邮件"和设备类型，生成16位密码
5. 将生成的密码（去掉空格）填入 `SMTP_PASSWORD`

**注意**: 必须启用两步验证才能生成应用专用密码。

### 2. 安装依赖

确保已安装邮件相关库：

```bash
pip install -r requirements.txt
```

### 3. 运行测试

```bash
python test_browseragent.py
```

测试流程：
1. Browser Agent 下载公告PDF
2. Email Agent 发送邮件（附带PDF）
3. 检查收件箱确认

---

## API 使用

### EmailAgent 类

```python
from email_agent import EmailAgent

agent = EmailAgent()
```

### send_task_result()

发送任务完成邮件的主要方法。

```python
success = agent.send_task_result(
    task_result: Dict,           # 任务结果字典
    recipient_email: str,        # 收件人邮箱
    user_name: str = "用户",     # 用户名
    include_downloads: bool = True,   # 是否附加下载文件
    include_screenshots: bool = True  # 是否附加截图
)
```

**参数说明**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `task_result` | Dict | ✅ | Browser Agent返回的任务结果 |
| `recipient_email` | str | ✅ | 收件人邮箱地址 |
| `user_name` | str | ❌ | 收件人姓名（默认"用户"） |
| `include_downloads` | bool | ❌ | 是否附加下载的文件（默认True） |
| `include_screenshots` | bool | ❌ | 是否附加截图（默认True） |

**返回值**:
- `True` - 邮件发送成功
- `False` - 邮件发送失败

### task_result 字段

Email Agent 需要的 `task_result` 字段：

```python
{
    'task_id': 6002,                    # 任务ID
    'query': '找到并下载...',           # 任务查询
    'summary': '已成功下载...',         # 任务摘要
    'source_url': 'https://...',       # 信息来源URL
    'downloaded_files': ['a.pdf'],     # 下载文件列表
    'download_count': 1,               # 下载文件数量
    'steps': [...],                    # 执行步骤（可选）
    'task_report_path': '...',         # 任务报告路径（可选）
    'created_at': '2025-10-28 ...'     # 创建时间（可选）
}
```

---

## 完整示例

### 示例1: 基本使用

```python
import asyncio
from browser_agent import BrowserAgent
from email_agent import EmailAgent

async def download_and_email():
    # 1. 执行浏览器任务
    browser_agent = BrowserAgent(api_key='sk-xxx')
    result = await browser_agent.execute_task(
        query="下载安克创新最新公告PDF",
        target_url="https://www.szse.cn/...",
        task_id=1001
    )

    # 2. 发送邮件
    if result['success']:
        email_agent = EmailAgent()
        email_agent.send_task_result(
            task_result=result,
            recipient_email='user@example.com',
            user_name='张三'
        )

asyncio.run(download_and_email())
```

### 示例2: 自定义附件

```python
email_agent = EmailAgent()

# 只发送下载文件，不附加截图
email_agent.send_task_result(
    task_result=result,
    recipient_email='user@example.com',
    include_downloads=True,      # 附加PDF
    include_screenshots=False    # 不附加截图
)
```

### 示例3: 预览邮件正文

```python
email_agent = EmailAgent()

# 生成邮件正文预览（纯文本）
body = email_agent.format_email_body(task_result)
print(body)
```

---

## 邮件内容

### 邮件主题

```
[VerifAIble] 您的查询任务已完成 - {任务查询前30字}
```

### 邮件结构

1. **头部**
   - VerifAIble Logo
   - "您的智能语音助手"副标题

2. **您的问题**
   - 显示用户的原始查询

3. **研究结果**
   - 任务摘要
   - 高亮显示关键信息

4. **下载文件**（如果有）
   - 显示下载文件数量
   - 说明已作为附件发送

5. **任务详情**
   - 信息来源（可点击链接）
   - 执行步骤数
   - 任务创建时间

6. **邮件附件**
   - 列出所有附件
   - 显示文件名、大小、类型
   - 使用图标区分文件类型：
     - 📄 PDF文档
     - 📸 截图
     - 🌐 网页报告
     - 📝 Markdown报告

7. **行动号召**
   - "点击接听语音汇报"按钮
   - 跳转到VerifAIble查看详情

### 邮件样式

- 响应式设计（适配手机和电脑）
- 清新的绿色主题色
- 圆角卡片布局
- 醒目的按钮和链接

---

## 附件处理

### 支持的文件类型

| 类型 | 扩展名 | 图标 | MIME类型 |
|------|--------|------|----------|
| PDF文档 | .pdf | 📄 | application/pdf |
| 图片 | .png, .jpg, .jpeg, .gif | 📸 | image/* |
| 网页 | .html, .htm | 🌐 | text/html |
| Markdown | .md | 📝 | text/markdown |

### 附件限制

- **截图**: 最多5张（避免邮件过大）
- **文件大小**: 建议单个附件 < 10MB
- **总大小**: 邮件总大小建议 < 25MB（Gmail限制）

### 附件优先级

1. 下载的PDF文件（业务核心）
2. 任务报告（重要）
3. 截图（可选，最多5张）

---

## 错误处理

### 常见错误

#### 1. SMTP认证失败

```
ERROR - 发送邮件失败: (535, b'5.7.8 Username and Password not accepted')
```

**解决方案**:
- 检查 `SMTP_USER` 和 `SMTP_PASSWORD` 是否正确
- Gmail需要使用应用专用密码，不是邮箱密码
- 确认已启用两步验证

#### 2. 附件不存在

```
WARNING - 附件不存在: /path/to/file.pdf
```

**解决方案**:
- 确认文件路径正确
- 检查下载任务是否成功完成
- 查看 `task_result['downloaded_files']` 是否有效

#### 3. 连接超时

```
ERROR - 发送邮件失败: TimeoutError
```

**解决方案**:
- 检查网络连接
- 确认SMTP服务器地址和端口正确
- 尝试使用其他网络（可能被防火墙拦截）

#### 4. 邮件过大

```
ERROR - Message too large (552, b'5.3.4 Message size exceeds fixed limit')
```

**解决方案**:
- 减少附件数量（设置 `include_screenshots=False`）
- 压缩PDF文件
- 分多封邮件发送

---

## 日志

Email Agent 会记录详细日志：

```python
2025-10-28 10:00:00 - email_agent - INFO - 📧 邮件代理已初始化
2025-10-28 10:00:01 - email_agent - INFO - 📧 开始发送任务结果邮件到: user@example.com
2025-10-28 10:00:01 - email_agent - INFO -    📎 附加下载文件: 公告.pdf
2025-10-28 10:00:01 - email_service - INFO -    📎 已附加文件: 公告.pdf
2025-10-28 10:00:02 - email_service - INFO - 邮件发送成功
2025-10-28 10:00:02 - email_agent - INFO - ✅ 邮件发送成功到: user@example.com
```

---

## 安全建议

### 1. 环境变量管理

```bash
# ✅ 正确 - 使用环境变量
export SMTP_PASSWORD="your_app_password"

# ❌ 错误 - 硬编码在代码中
SMTP_PASSWORD = "your_app_password"  # 不要这样做！
```

### 2. .env 文件保护

```bash
# 添加到 .gitignore
echo ".env" >> .gitignore

# 设置文件权限（仅所有者可读写）
chmod 600 .env
```

### 3. 应用专用密码

- ✅ 使用应用专用密码（Gmail、Outlook等）
- ❌ 不要使用邮箱主密码
- ✅ 定期更换密码
- ✅ 不同应用使用不同的专用密码

### 4. 敏感信息处理

Email Agent **不会**在邮件中包含：
- API密钥
- 密码
- 个人身份信息（除非明确在任务结果中）

---

## 进阶配置

### 使用其他邮件服务

#### Outlook/Hotmail

```bash
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=your_email@outlook.com
SMTP_PASSWORD=your_password
```

#### QQ邮箱

```bash
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your_email@qq.com
SMTP_PASSWORD=your_authorization_code  # 需要生成授权码
```

#### 163邮箱

```bash
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=your_email@163.com
SMTP_PASSWORD=your_authorization_code
```

### 自定义邮件模板

如果需要自定义邮件样式，修改 `email_service.py` 中的 `_generate_result_email_html()` 方法。

---

## 测试

### 单元测试

```bash
# 测试 Email Agent
python email_agent.py

# 测试 Email Service
python email_service.py
```

### 集成测试

```bash
# 完整流程测试（下载 + 邮件）
python test_browseragent.py
```

### 检查清单

- [ ] 环境变量已配置
- [ ] SMTP凭据正确
- [ ] 收件人邮箱有效
- [ ] 下载目录存在且有文件
- [ ] 网络连接正常
- [ ] 防火墙未拦截SMTP端口

---

## 性能优化

### 1. 减少附件大小

```python
# 只发送PDF，不发送截图
email_agent.send_task_result(
    task_result=result,
    recipient_email=email,
    include_downloads=True,
    include_screenshots=False  # 节省带宽
)
```

### 2. 异步发送（未来）

当前版本是同步发送，如果需要批量发送可考虑：
- 使用消息队列（Celery + Redis）
- 异步SMTP库（aiosmtplib）

### 3. 重试机制（未来）

对于临时网络问题，可以添加重试：
```python
# 伪代码
max_retries = 3
for attempt in range(max_retries):
    try:
        send_email()
        break
    except TemporaryError:
        wait(2 ** attempt)  # 指数退避
```

---

## FAQ

### Q1: 为什么邮件发送失败？

**A**: 最常见的原因是SMTP配置错误。请检查：
1. SMTP服务器地址和端口
2. 邮箱账号和密码（应用专用密码）
3. 网络连接和防火墙设置

### Q2: Gmail一直报认证错误？

**A**: Gmail需要使用应用专用密码，不是邮箱密码。必须先启用两步验证，然后在"安全性"设置中生成应用专用密码。

### Q3: 邮件能发送但附件丢失？

**A**: 检查文件路径是否正确，确认下载任务成功完成。查看日志中是否有"附件不存在"的警告。

### Q4: 可以发送给多个收件人吗？

**A**: 可以。修改代码传入邮箱列表：
```python
email_service.send_task_result_email(
    to_emails=['user1@example.com', 'user2@example.com'],
    ...
)
```

### Q5: 如何自定义邮件样式？

**A**: 编辑 `email_service.py` 中的 `_generate_result_email_html()` 方法，修改HTML和CSS。

### Q6: 支持HTML格式的任务摘要吗？

**A**: 当前只支持纯文本。如果需要富文本格式，可以在 `summary` 中使用Markdown，然后在模板中转换为HTML。

---

## 相关文档

- `email_service.py` - 底层SMTP邮件服务
- `email_agent.py` - 邮件代理实现
- `test_browseragent.py` - 完整测试示例
- `.env.example` - 环境变量配置模板

---

## 技术栈

- **邮件发送**: Python `smtplib` (标准库)
- **邮件格式**: `email.mime` (标准库)
- **HTML模板**: 内联CSS（兼容性最好）
- **日志**: Python `logging` (标准库)

---

## 更新日志

### v1.0.0 (2025-10-28)

- ✨ 创建独立的 Email Agent
- ✨ 支持附加PDF文件和截图
- ✨ 新邮件模板（包含文件来源链接）
- ✨ 自动文件类型识别
- ✨ 详细的附件列表展示
- 📝 完整的使用文档

---

**作者**: Claude Code
**更新日期**: 2025-10-28
