# BrowserAgent & EmailAgent 部署指南

## 概述

已成功将 BrowserAgent 和 EmailAgent 集成到 VerifAIble 服务器中。用户的自然语言查询会经过以下流程：

```
用户语音输入
  → OpenAI Realtime API (语音识别)
  → 意图识别神经网络 (映射到URL)
  → BrowserAgent (执行浏览器任务)
  → EmailAgent (发送结果邮件)
```

## 架构说明

### 1. 意图识别 → URL映射
- **端点**: `POST /recognize_intent`
- **功能**: 将用户查询映射到目标网址
- **返回**: `{ "url": "https://...", "confidence": 0.95 }`

### 2. 深度搜索任务
- **端点**: `POST /deep_search`
- **功能**: 创建异步任务，执行浏览器自动化
- **流程**:
  1. 调用意图识别获取目标URL
  2. 创建Task记录（status='pending'）
  3. 启动后台线程执行 `_execute_deep_search_task`
  4. 返回 task_id 供前端轮询

### 3. BrowserAgent 执行
- **文件**: `browser_agent.py`
- **功能**:
  - 使用 Playwright 控制浏览器
  - 通过 OpenAI GPT-4o 进行决策
  - 截图记录每一步操作
  - 自动下载PDF等文件到 `downloads/` 目录
  - 生成任务报告 (`task_data/reports/`)

### 4. EmailAgent 发送
- **文件**: `email_agent.py`
- **功能**:
  - 格式化任务结果为HTML邮件
  - 附加下载的PDF文件
  - 附加操作截图（最多5张）
  - 附加任务报告 (Markdown)
  - 支持多收件人

## 数据库变更

### Task 表新增字段

```python
downloaded_files = db.Column(db.Text)  # JSON数组，下载的文件路径列表
```

**迁移脚本**: `migrate_add_downloaded_files.py`

运行迁移：
```bash
python migrate_add_downloaded_files.py
```

## 环境变量配置

确保 `.env` 文件包含以下配置：

```bash
# OpenAI API
OPENAI_API_KEY=sk-proj-...

# 数据库
DATABASE_URL=sqlite:///verifaible.db

# SMTP邮件配置
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your_email@qq.com
SMTP_PASSWORD=your_smtp_password
FROM_EMAIL=your_email@qq.com
FROM_NAME=VerifAIble

# 用户名（开发测试用，生产环境从数据库读取）
USER_NAME=用户
```

## 服务器部署步骤

### 1. 准备环境

```bash
cd /path/to/VerifAIble

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置文件
vim .env
```

### 3. 初始化数据库

```bash
# 启动服务器会自动创建表
python websocket_server.py

# 或手动初始化
python init_db.py
```

### 4. 运行迁移（如果数据库已存在）

```bash
python migrate_add_downloaded_files.py
```

### 5. 测试集成

**测试 BrowserAgent 独立运行**:
```bash
python test_browseragent.py
```

**测试 EmailAgent 独立运行**:
```bash
python test_email_only.py
```

**测试完整流程**:
```bash
# 启动服务器
python websocket_server.py

# 在另一个终端测试API
curl -X POST http://localhost:3001/deep_search \
  -H "Content-Type: application/json" \
  -d '{"query": "帮我查一下安克创新最新的公告"}'
```

### 6. 生产部署（verifaible.space）

#### 使用 Supervisor 管理进程

创建 `/etc/supervisor/conf.d/verifaible.conf`:

```ini
[program:verifaible]
command=/path/to/venv/bin/python /path/to/VerifAIble/websocket_server.py
directory=/path/to/VerifAIble
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/verifaible/error.log
stdout_logfile=/var/log/verifaible/access.log
environment=PATH="/path/to/venv/bin"
```

启动服务：
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start verifaible
```

#### 使用 Nginx 反向代理

创建 `/etc/nginx/sites-available/verifaible.space`:

```nginx
server {
    listen 80;
    server_name verifaible.space;

    location / {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 静态文件目录（截图、下载文件等）
    location /downloads/ {
        alias /path/to/VerifAIble/downloads/;
    }

    location /task_data/ {
        alias /path/to/VerifAIble/task_data/;
    }
}
```

启用站点并重启：
```bash
sudo ln -s /etc/nginx/sites-available/verifaible.space /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 配置HTTPS（Let's Encrypt）

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d verifaible.space
```

## API 接口文档

### 创建深度搜索任务

**请求**:
```http
POST /deep_search
Content-Type: application/json
Cookie: session=...

{
  "query": "帮我查一下安克创新最新的公告"
}
```

**响应**:
```json
{
  "success": true,
  "task_id": 123,
  "target_url": "https://www.szse.cn/disclosure/listed/notice/index.html",
  "message": "任务已创建，正在后台执行中..."
}
```

### 查询任务状态

**请求**:
```http
GET /tasks/123
Cookie: session=...
```

**响应**:
```json
{
  "id": 123,
  "query": "帮我查一下安克创新最新的公告",
  "target_url": "https://www.szse.cn/...",
  "status": "completed",
  "summary": "已找到安克创新最新公告...",
  "source_url": "https://...",
  "step_count": 5,
  "created_at": "2025-10-28T10:00:00",
  "completed_at": "2025-10-28T10:02:30",
  "email_sent": true,
  "is_read": false
}
```

## 邮件发送逻辑

### 收件人确定
1. 优先使用用户配置的 `notification_emails`（可配置多个）
2. 如果未配置，使用 Google OAuth 登录邮箱

### 附件内容
1. **下载的文件**: 所有PDF等业务文件
2. **截图**: 最多5张操作截图
3. **任务报告**: Markdown格式的详细报告

### 发送时机
- 任务状态变为 `completed` 后立即发送
- 如果发送成功，`task.email_sent = True`

## 监控和日志

### 日志文件位置
```
/var/log/verifaible/
  ├── access.log    # 标准输出
  └── error.log     # 错误日志
```

### 查看实时日志
```bash
# Supervisor 日志
sudo tail -f /var/log/verifaible/error.log

# 应用日志（如果配置了文件日志）
tail -f /path/to/VerifAIble/logs/app.log
```

### 监控任务状态
```bash
# 查看数据库中的任务
sqlite3 verifaible.db "SELECT id, status, query, created_at FROM tasks ORDER BY id DESC LIMIT 10;"
```

## 故障排查

### BrowserAgent 无法启动
```bash
# 检查 Playwright 是否正确安装
playwright install --with-deps chromium

# 测试浏览器
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); print('OK')"
```

### 邮件发送失败
```bash
# 测试SMTP连接
python test_email_only.py

# 检查SMTP配置
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('SMTP_HOST'))"
```

### 下载文件丢失
- 检查 `downloads/` 目录权限
- 确保服务器有足够磁盘空间
- 查看 BrowserAgent 日志确认下载是否成功

## 性能优化建议

### 1. 并发任务限制
在 `websocket_server.py` 中添加任务队列：
```python
from queue import Queue
import threading

task_queue = Queue(maxsize=10)
worker_threads = []

for _ in range(3):  # 最多3个并发任务
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    worker_threads.append(t)
```

### 2. 文件清理
定期清理旧的下载文件和截图：
```bash
# 添加到 crontab
0 2 * * * find /path/to/VerifAIble/downloads -mtime +7 -delete
0 2 * * * find /path/to/VerifAIble/task_data/reports -mtime +30 -delete
```

### 3. 数据库优化
```bash
# 定期优化数据库
sqlite3 verifaible.db "VACUUM;"

# 添加索引
sqlite3 verifaible.db "CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);"
```

## 安全注意事项

1. **API密钥保护**: 确保 `.env` 文件权限为 `600`
2. **用户认证**: 所有API端点都应使用 `@require_auth` 装饰器
3. **文件访问控制**: 确保用户只能访问自己的下载文件
4. **速率限制**: 考虑添加 Flask-Limiter 防止滥用

## 联系支持

如有问题，请查看：
- GitHub Issues: https://github.com/your-repo/issues
- 文档: https://docs.verifaible.space
