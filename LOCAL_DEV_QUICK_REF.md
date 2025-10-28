# 本地开发环境快速参考

## 🚀 一键配置

```bash
# 运行配置向导
python setup_local_dev.py
```

这会自动：
- ✅ 生成加密密钥
- ✅ 创建 .env 文件
- ✅ 检查依赖
- ✅ 初始化数据库

---

## 📝 必须手动配置的 3 项

### 1. Google OAuth（5分钟）

访问：https://console.cloud.google.com/

1. 创建项目 → API 和服务 → 凭据
2. 创建 OAuth 客户端 ID（Web 应用）
3. 重定向 URI：`http://localhost:3001/auth/callback`
4. 复制客户端 ID 和密钥到 `.env`

### 2. OpenAI API Key

访问：https://platform.openai.com/api-keys

复制到 `.env` 的 `OPENAI_API_KEY`

### 3. SMTP 邮件（QQ邮箱）

1. QQ邮箱 → 设置 → 账户 → POP3/IMAP/SMTP
2. 开启服务 → 生成授权码（16位）
3. 复制授权码到 `.env` 的 `SMTP_PASSWORD`

---

## 🎬 启动开发

```bash
# 启动服务器
python websocket_server.py

# 访问
http://localhost:3001
```

---

## 🧪 测试

```bash
# 完整集成测试（推荐）
python test_server_integration.py

# 观察浏览器操作
python test_browseragent.py

# 测试邮件
python test_email_only.py
```

---

## 🗄️ 数据库

```bash
# 查看数据
sqlite3 verifaible.db "SELECT * FROM users;"
sqlite3 verifaible.db "SELECT * FROM tasks;"

# 重置数据库
rm verifaible.db && python init_db.py
```

---

## 🐛 常见问题

### Google 登录失败
- 检查重定向 URI 是否正确：`http://localhost:3001/auth/callback`
- 确保添加了测试用户（如果是外部应用）

### 端口被占用
```bash
lsof -i :3001
kill -9 <PID>
```

### 邮件发送失败
- SMTP_PASSWORD 必须是**授权码**（不是邮箱密码）
- 运行 `python test_email_only.py` 测试

---

## 📂 重要文件

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置 |
| `verifaible.db` | SQLite 数据库 |
| `websocket_server.py` | Flask 服务器 |
| `static/websocket.html` | 前端主页 |

---

## 📚 详细文档

- **完整配置**: `LOCAL_DEVELOPMENT_SETUP.md`
- **测试指南**: `LOCAL_TEST_GUIDE.md`
- **部署指南**: `SERVER_DEPLOYMENT.md`

---

## ✅ 功能清单

本地开发环境支持：
- ✅ Google OAuth 登录
- ✅ SQLite 数据库
- ✅ BrowserAgent 浏览器自动化
- ✅ EmailAgent 邮件发送
- ✅ 意图识别 API
- ✅ WebSocket 实时通信
- ✅ 前端界面

**与生产环境完全一致！** 🎉
