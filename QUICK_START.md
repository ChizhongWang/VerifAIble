# ⚡ 快速开始指南

## 服务器部署（3步完成）

### 步骤 1: 登录服务器并进入项目目录
```bash
ssh user@verifaible.space
cd /var/www/verifaible  # 或你的项目路径
```

### 步骤 2: 拉取最新代码
```bash
git pull origin main
```

### 步骤 3: 运行部署脚本
```bash
bash deploy_to_server.sh
```

**完成！** 🎉 脚本会自动完成所有部署步骤并重启服务。

---

## 如果是首次部署

### 1. 克隆代码
```bash
cd /var/www
git clone https://github.com/ChizhongWang/VerifAIble.git
cd VerifAIble
```

### 2. 配置环境变量
```bash
cp .env.example .env
vim .env  # 填入你的配置
```

**必须配置：**
- `OPENAI_API_KEY` - OpenAI API 密钥
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` - 邮件服务器配置
- `SECRET_KEY` - 随机密钥

### 3. 创建虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. 安装依赖
```bash
pip install -r requirements.txt
playwright install chromium
```

### 5. 配置 Supervisor（服务管理）
```bash
sudo vim /etc/supervisor/conf.d/verifaible.conf
```

内容：
```ini
[program:verifaible]
command=/var/www/VerifAIble/venv/bin/python /var/www/VerifAIble/websocket_server.py
directory=/var/www/VerifAIble
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/verifaible/error.log
stdout_logfile=/var/log/verifaible/access.log
```

启动：
```bash
sudo mkdir -p /var/log/verifaible
sudo chown www-data:www-data /var/log/verifaible
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start verifaible
```

### 6. 配置 Nginx（可选但推荐）
```bash
sudo vim /etc/nginx/sites-available/verifaible.space
```

添加反向代理配置（见 `SERVER_DEPLOYMENT.md`），然后：
```bash
sudo ln -s /etc/nginx/sites-available/verifaible.space /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. 配置 HTTPS
```bash
sudo certbot --nginx -d verifaible.space
```

---

## 验证部署

### 检查服务状态
```bash
sudo supervisorctl status verifaible
# 应该显示: RUNNING
```

### 测试健康检查
```bash
curl https://verifaible.space/health
# 应该返回: {"status":"healthy","service":"OpenAI Realtime WebSocket Server"}
```

### 查看日志
```bash
tail -f /var/log/verifaible/error.log
```

---

## 常用命令

### 重启服务
```bash
sudo supervisorctl restart verifaible
```

### 查看日志
```bash
# 实时查看
tail -f /var/log/verifaible/error.log

# 查看最近50行
tail -n 50 /var/log/verifaible/error.log
```

### 查看任务
```bash
sqlite3 verifaible.db "SELECT id, status, query FROM tasks ORDER BY id DESC LIMIT 5;"
```

### 手动运行测试
```bash
cd /var/www/VerifAIble
source venv/bin/activate
python test_email_only.py  # 测试邮件
python check_deployment.py  # 检查配置
```

---

## 故障排查

### 服务无法启动
```bash
# 查看错误详情
sudo supervisorctl tail -f verifaible stderr

# 检查端口占用
sudo lsof -i :3001

# 手动启动测试
cd /var/www/VerifAIble
source venv/bin/activate
python websocket_server.py
```

### 邮件发送失败
```bash
# 测试邮件配置
python test_email_only.py

# 检查 SMTP 密码是否为授权码（不是邮箱密码）
```

### 浏览器任务失败
```bash
# 重新安装浏览器
playwright install chromium

# 检查系统依赖
playwright install-deps
```

---

## 需要详细文档？

- **完整部署指南**: `SERVER_DEPLOYMENT.md`
- **部署检查清单**: `DEPLOYMENT_CHECKLIST.md`
- **集成说明**: `INTEGRATION_SUMMARY.md`
- **BrowserAgent 文档**: `BROWSER_AGENT_DEPLOYMENT.md`

---

## 🎯 最简部署（已配置服务器）

对于已经配置好的服务器，每次更新只需要：

```bash
ssh user@verifaible.space
cd /var/www/VerifAIble
bash deploy_to_server.sh
```

**就这么简单！** ✨
