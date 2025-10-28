# VerifAIble 快速部署指南

## 🎯 系统架构

```
用户语音 → Realtime API → 意图识别 → BrowserAgent → EmailAgent → 用户邮箱
                ↓            ↓             ↓            ↓
              转文本       获取URL      自动操作    发送结果
```

## 📦 准备工作

### 1. 克隆代码
```bash
git clone https://github.com/your-repo/VerifAIble.git
cd VerifAIble
```

### 2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. 配置环境变量
```bash
cp .env.example .env
vim .env  # 填入你的配置
```

必填配置：
```bash
OPENAI_API_KEY=sk-proj-...        # OpenAI API密钥
SMTP_HOST=smtp.qq.com              # QQ邮箱SMTP
SMTP_PORT=587
SMTP_USER=your_email@qq.com        # 发件邮箱
SMTP_PASSWORD=授权码               # SMTP授权码（不是邮箱密码）
FROM_EMAIL=your_email@qq.com
RECIPIENT_EMAIL=recipient@qq.com   # 接收邮件的邮箱
USER_NAME=王先生                    # 用户称呼
```

## ✅ 部署检查

运行自动检查脚本：
```bash
python check_deployment.py
```

应该看到：
```
✅ 所有检查通过！可以启动服务器
```

## 🚀 启动服务

### 开发环境
```bash
python websocket_server.py
```

访问：`http://localhost:3001`

### 生产环境（使用 Supervisor）

1. 创建配置文件 `/etc/supervisor/conf.d/verifaible.conf`：
```ini
[program:verifaible]
command=/path/to/venv/bin/python /path/to/VerifAIble/websocket_server.py
directory=/path/to/VerifAIble
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/verifaible/error.log
stdout_logfile=/var/log/verifaible/access.log
```

2. 启动服务：
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start verifaible
```

### Nginx 反向代理

创建 `/etc/nginx/sites-available/verifaible.space`：
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
    }
}
```

启用并重启：
```bash
sudo ln -s /etc/nginx/sites-available/verifaible.space /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### HTTPS（Let's Encrypt）
```bash
sudo certbot --nginx -d verifaible.space
```

## 🧪 测试

### 1. 测试 BrowserAgent 独立运行
```bash
python test_browseragent.py
```

### 2. 测试 EmailAgent 独立运行
```bash
python test_email_only.py
```

### 3. 测试完整集成
```bash
python test_server_integration.py
```

### 4. 测试 API 接口
```bash
# 需要先登录获取session cookie
curl -X POST http://localhost:3001/deep_search \
  -H "Content-Type: application/json" \
  -H "Cookie: session=..." \
  -d '{"query": "帮我查一下安克创新最新的公告"}'
```

## 📊 监控

### 查看日志
```bash
# Supervisor日志
tail -f /var/log/verifaible/error.log

# 应用日志（如果配置了）
tail -f logs/app.log
```

### 查看任务状态
```bash
sqlite3 verifaible.db "SELECT id, status, query, created_at FROM tasks ORDER BY id DESC LIMIT 10;"
```

### 查看系统状态
```bash
sudo supervisorctl status verifaible
```

## 🔧 常见问题

### Q1: 浏览器启动失败
```bash
playwright install --with-deps chromium
```

### Q2: 邮件发送失败
- 检查SMTP密码是否为**授权码**（不是邮箱密码）
- QQ邮箱需开启SMTP服务（设置→账户→POP3/IMAP/SMTP）
- 运行 `python test_email_only.py` 测试

### Q3: 数据库字段错误
```bash
python migrate_add_downloaded_files.py
```

### Q4: 端口被占用
修改 `websocket_server.py` 中的端口号，或停止占用进程：
```bash
lsof -i :3001
kill -9 <PID>
```

## 📚 相关文档

- **完整部署指南**: `BROWSER_AGENT_DEPLOYMENT.md`
- **集成总结**: `INTEGRATION_SUMMARY.md`
- **邮件集成指南**: `EMAIL_INTEGRATION_SUMMARY.md`
- **任务框架文档**: `TASK_FRAMEWORK.md`

## 🛠️ 开发测试

### 运行单元测试
```bash
python -m pytest tests/
```

### 调试模式
修改 `websocket_server.py`：
```python
app.run(debug=True, host='0.0.0.0', port=3001)
```

### 查看详细日志
修改日志级别：
```python
logging.basicConfig(level=logging.DEBUG)
```

## 🔒 安全建议

1. **保护环境变量文件**
```bash
chmod 600 .env
```

2. **使用HTTPS**
```bash
sudo certbot --nginx -d verifaible.space
```

3. **限制文件访问**
```nginx
location /downloads/ {
    # 添加认证
    auth_request /auth;
}
```

4. **定期清理旧文件**
```bash
# 添加到 crontab
0 2 * * * find /path/to/downloads -mtime +7 -delete
```

## 📞 获取帮助

- **问题报告**: GitHub Issues
- **文档**: `docs/` 目录
- **示例**: `examples/` 目录

---

**最后更新**: 2025-10-28
**版本**: v1.0.0
