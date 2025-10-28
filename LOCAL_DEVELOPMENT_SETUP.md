# 本地开发环境完整配置指南

## 🎯 目标

在本地完全模拟服务器环境，包括：
- ✅ SQLite 数据库
- ✅ Google OAuth 登录
- ✅ BrowserAgent 任务执行
- ✅ EmailAgent 邮件发送
- ✅ 完整的前后端交互

---

## 📋 配置步骤

### 1. Google OAuth 配置（支持本地开发）

#### 步骤 1.1: 创建 Google Cloud 项目

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 项目名称：`VerifAIble-Dev`（或任意名称）

#### 步骤 1.2: 启用 Google+ API

1. 在左侧菜单选择 **API 和服务 → 库**
2. 搜索 **Google+ API**
3. 点击**启用**

#### 步骤 1.3: 创建 OAuth 2.0 凭据

1. 在左侧菜单选择 **API 和服务 → 凭据**
2. 点击 **创建凭据 → OAuth 客户端 ID**
3. 应用类型：选择 **Web 应用**
4. 名称：`VerifAIble Local Dev`

5. **已获授权的 JavaScript 来源**：
   ```
   http://localhost:3001
   http://127.0.0.1:3001
   ```

6. **已获授权的重定向 URI**：
   ```
   http://localhost:3001/auth/callback
   http://127.0.0.1:3001/auth/callback
   ```

7. 点击**创建**

8. 记下：
   - **客户端 ID**（以 `.apps.googleusercontent.com` 结尾）
   - **客户端密钥**

#### 步骤 1.4: 配置测试用户（开发阶段）

1. 在左侧菜单选择 **OAuth 同意屏幕**
2. 如果是**外部**用户类型，需要添加测试用户：
   - 滚动到**测试用户**部分
   - 点击**添加用户**
   - 输入你的 Google 邮箱（用于测试登录）
   - 保存

---

### 2. 更新本地环境变量

编辑 `.env` 文件，添加 Google OAuth 配置：

```bash
# OpenAI API
OPENAI_API_KEY=sk-proj-...

# 数据库（本地开发使用 SQLite）
DATABASE_URL=sqlite:///verifaible.db

# Google OAuth（本地开发）
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret

# 加密密钥（用于加密存储用户的 API 密钥）
# 使用以下命令生成：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your_encryption_key_here

# Flask 配置
SECRET_KEY=your_secret_key_here
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
```

#### 生成加密密钥

```bash
# 生成 ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 生成 SECRET_KEY
python -c "import os; print(os.urandom(24).hex())"
```

将生成的密钥复制到 `.env` 文件中。

---

### 3. 初始化本地数据库

```bash
# 删除旧数据库（如果存在）
rm -f verifaible.db

# 创建新数据库和表
python init_db.py

# 运行迁移（添加新字段）
python migrate_add_downloaded_files.py
```

验证数据库：
```bash
sqlite3 verifaible.db ".tables"
# 应该显示：conversations  messages  tasks  tool_calls  users
```

---

### 4. 启动本地服务器

```bash
python websocket_server.py
```

应该看到：
```
2025-10-28 14:53:21,652 - __main__ - INFO - 数据库表已创建
2025-10-28 14:53:21,655 - __main__ - INFO - 启动WebSocket服务器，端口: 3001
 * Running on http://127.0.0.1:3001
```

---

### 5. 测试 Google 登录

#### 步骤 5.1: 访问应用

在浏览器打开：**http://localhost:3001**

会自动重定向到登录页面。

#### 步骤 5.2: 点击 Google 登录

点击"使用 Google 登录"按钮。

#### 步骤 5.3: 完成 Google 授权

1. 选择你的 Google 账号（需要是之前添加的测试用户）
2. 允许权限：
   - 查看你的电子邮件地址
   - 查看你的个人信息
3. 授权后会自动跳转回 `http://localhost:3001/auth/callback`
4. 成功后重定向到主页

#### 步骤 5.4: 配置 OpenAI API 密钥

1. 首次登录会跳转到设置页面（`/settings`）
2. 输入你的 OpenAI API 密钥
3. 保存

---

### 6. 测试完整功能

#### 方案 A: 通过 Web 界面

1. 登录后访问主页：http://localhost:3001
2. 使用语音或文本输入查询：
   ```
   帮我查一下安克创新最新的公告
   ```
3. 系统会：
   - 识别意图 → 获取目标 URL
   - 创建任务 → 后台执行
   - BrowserAgent 自动操作浏览器
   - 下载 PDF 文件
   - EmailAgent 发送邮件通知

#### 方案 B: 通过 API 测试

使用 `curl` 或 Postman 测试（需要先登录获取 session cookie）：

**获取 Session Cookie：**
1. 在浏览器中登录
2. 打开开发者工具（F12）
3. Application → Cookies → http://localhost:3001
4. 复制 `session` cookie 的值

**测试深度搜索 API：**
```bash
curl -X POST http://localhost:3001/deep_search \
  -H "Content-Type: application/json" \
  -H "Cookie: session=YOUR_SESSION_COOKIE" \
  -d '{
    "query": "帮我查一下安克创新最新的公告"
  }'
```

**查询任务状态：**
```bash
curl http://localhost:3001/tasks/1 \
  -H "Cookie: session=YOUR_SESSION_COOKIE"
```

#### 方案 C: 使用测试脚本（绕过认证）

临时修改 `websocket_server.py` 用于测试：

```python
@app.route('/deep_search', methods=['POST'])
# @require_auth  # 临时注释掉
def deep_search():
    # ...
    # 临时硬编码测试用户
    user_id = 1  # 添加这行
    # user_id = session['user_id']  # 注释掉这行
```

然后运行：
```bash
python test_server_integration.py
```

---

## 🗄️ 本地数据库管理

### 查看数据库

```bash
# 进入 SQLite 命令行
sqlite3 verifaible.db

# 查看所有表
.tables

# 查看用户表
SELECT * FROM users;

# 查看任务表
SELECT id, status, query, created_at FROM tasks;

# 退出
.quit
```

### 重置数据库

```bash
# 备份（可选）
cp verifaible.db verifaible_backup.db

# 删除
rm verifaible.db

# 重新创建
python init_db.py
python migrate_add_downloaded_files.py
```

### 添加测试数据

创建测试用户和任务：

```bash
sqlite3 verifaible.db <<EOF
INSERT INTO users (google_id, email, name, created_at, last_login)
VALUES ('test123', 'test@example.com', '测试用户', datetime('now'), datetime('now'));

INSERT INTO tasks (user_id, query, target_url, status, created_at)
VALUES (1, '测试查询', 'https://example.com', 'pending', datetime('now'));
EOF
```

---

## 🔍 调试技巧

### 1. 启用详细日志

修改 `websocket_server.py`：

```python
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 2. 使用 Flask Debug 模式

`.env` 文件中设置：
```bash
DEBUG=True
```

这样代码修改后会自动重启服务器。

### 3. 查看实时日志

```bash
# 启动服务器并输出到文件
python websocket_server.py 2>&1 | tee server.log

# 在另一个终端查看日志
tail -f server.log
```

### 4. 使用 Python 调试器

在代码中插入断点：

```python
import pdb; pdb.set_trace()
```

### 5. 测试邮件发送

```bash
python test_email_only.py
```

### 6. 测试浏览器任务

```bash
# 有头模式（可以看到浏览器操作）
python test_browseragent.py

# 无头模式
python test_server_integration.py
```

---

## 📂 本地开发目录结构

```
VerifAIble/
├── verifaible.db              # 本地 SQLite 数据库
├── .env                        # 本地环境变量（包含 Google OAuth）
├── downloads/                  # 下载的文件
├── task_data/                  # 任务数据
│   └── reports/               # 任务报告
├── logs/                       # 日志文件
├── backups/                    # 数据库备份
├── static/                     # 前端静态文件
│   ├── websocket.html         # 主界面
│   ├── login.html             # 登录页面
│   └── settings.html          # 设置页面
├── websocket_server.py        # Flask 服务器
├── auth.py                     # Google OAuth 认证
├── models.py                   # 数据库模型
├── browser_agent.py           # 浏览器代理
├── email_agent.py             # 邮件代理
└── test_*.py                   # 测试脚本
```

---

## 🔄 开发工作流程

### 1. 启动开发环境

```bash
# 激活虚拟环境
source venv/bin/activate  # 或 source VerifAIble/bin/activate

# 启动服务器
python websocket_server.py
```

### 2. 修改代码

在 IDE 中编辑代码，Flask Debug 模式会自动重启。

### 3. 测试修改

- **前端测试**：刷新浏览器
- **后端测试**：运行测试脚本或使用 API

### 4. 提交代码

```bash
git add .
git commit -m "Your commit message"
git push origin main
```

### 5. 部署到服务器

```bash
# SSH 到服务器
ssh user@verifaible.space

# 进入项目目录
cd /var/www/verifaible

# 运行部署脚本
bash deploy_to_server.sh
```

---

## 🆚 本地开发 vs 生产环境

| 配置项 | 本地开发 | 生产环境 |
|--------|---------|---------|
| 数据库 | SQLite | SQLite / PostgreSQL |
| HTTP/HTTPS | HTTP | HTTPS (Let's Encrypt) |
| DEBUG | True | False |
| Google OAuth 回调 | http://localhost:3001/auth/callback | https://verifaible.space/auth/callback |
| 服务器 | Flask built-in | Gunicorn + Nginx + Supervisor |
| 日志 | 控制台输出 | 文件 + 日志轮转 |

---

## ⚠️ 常见问题

### Q1: Google OAuth 回调失败

**症状**：点击登录后跳转到错误页面

**解决方案**：
1. 检查 Google Cloud Console 中的重定向 URI 是否正确
2. 确保使用 `http://localhost:3001/auth/callback`（不是 `127.0.0.1`）
3. 确保是测试用户（如果应用处于测试模式）

### Q2: 数据库表不存在

**症状**：`no such table: users`

**解决方案**：
```bash
rm verifaible.db
python init_db.py
python migrate_add_downloaded_files.py
```

### Q3: Session 过期

**症状**：刷新页面后需要重新登录

**解决方案**：
- 这是正常的，开发模式下 session 默认是短期的
- 可以在 `.env` 中设置：
  ```bash
  PERMANENT_SESSION_LIFETIME=86400  # 24小时
  ```

### Q4: 端口被占用

**症状**：`Address already in use`

**解决方案**：
```bash
# 查找占用进程
lsof -i :3001

# 杀死进程
kill -9 <PID>

# 或更改端口
# 修改 websocket_server.py 中的 port = 3001
```

---

## 🚀 生产环境部署

本地开发测试通过后，部署到服务器：

1. **更新 Google OAuth 配置**：
   - 在 Google Cloud Console 添加生产环境回调 URL
   - `https://verifaible.space/auth/callback`

2. **更新服务器 .env**：
   ```bash
   HTTPS=True
   DEBUG=False
   ```

3. **运行部署脚本**：
   ```bash
   bash deploy_to_server.sh
   ```

详细步骤见：`SERVER_DEPLOYMENT.md`

---

## 📝 开发检查清单

- [ ] Google OAuth 配置完成
- [ ] 本地环境变量配置完成
- [ ] 数据库初始化成功
- [ ] 可以正常登录
- [ ] 可以设置 API 密钥
- [ ] 可以创建任务
- [ ] BrowserAgent 运行正常
- [ ] EmailAgent 发送成功
- [ ] 前端界面正常显示
- [ ] 所有测试脚本通过

---

**完成以上配置后，你就拥有了一个完整的本地开发环境！** 🎉

所有功能都可以在本地测试，然后一键部署到服务器。
