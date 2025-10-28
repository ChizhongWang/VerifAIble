# 服务器部署步骤（verifaible.space）

## 快速部署（推荐）

### 1. 登录服务器
```bash
ssh user@verifaible.space
```

### 2. 进入项目目录
```bash
cd /path/to/VerifAIble
```

### 3. 运行部署脚本
```bash
bash deploy_to_server.sh
```

**脚本会自动完成：**
- ✅ 备份数据库和配置文件
- ✅ 拉取最新代码
- ✅ 更新依赖
- ✅ 运行数据库迁移
- ✅ 执行部署检查
- ✅ 重启服务

## 手动部署（详细步骤）

### 步骤 1: 备份数据

```bash
# 备份数据库
mkdir -p backups
cp verifaible.db backups/verifaible_$(date +%Y%m%d_%H%M%S).db

# 备份配置
cp .env .env.backup
```

### 步骤 2: 拉取代码

```bash
# 保存本地修改
git stash

# 拉取最新代码
git pull origin main

# 或强制拉取（会覆盖本地修改）
git fetch --all
git reset --hard origin/main

# 恢复 .env 配置
cp .env.backup .env
```

### 步骤 3: 更新依赖

```bash
# 激活虚拟环境
source venv/bin/activate  # 或 source VerifAIble/bin/activate

# 更新 Python 依赖
pip install -r requirements.txt

# 确保 Playwright 浏览器已安装
playwright install chromium
```

### 步骤 4: 数据库迁移

```bash
# 运行迁移脚本（添加 downloaded_files 字段）
python migrate_add_downloaded_files.py
```

### 步骤 5: 部署检查

```bash
# 运行检查脚本
python check_deployment.py
```

应该看到：
```
✅ 所有检查通过！可以启动服务器
```

### 步骤 6: 重启服务

**使用 Supervisor（推荐）：**
```bash
sudo supervisorctl restart verifaible
sudo supervisorctl status verifaible
```

**手动重启：**
```bash
# 停止旧进程
pkill -f websocket_server.py

# 启动新进程
nohup python websocket_server.py > logs/server.log 2>&1 &
```

### 步骤 7: 验证部署

```bash
# 查看服务状态
sudo supervisorctl status verifaible

# 查看日志
tail -f /var/log/verifaible/error.log

# 测试 API
curl https://verifaible.space/health
```

## 环境变量配置

确保服务器上的 `.env` 文件包含以下配置：

```bash
# OpenAI API
OPENAI_API_KEY=sk-proj-...

# 数据库
DATABASE_URL=sqlite:///verifaible.db

# SMTP邮件配置（QQ邮箱）
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your_email@qq.com
SMTP_PASSWORD=your_smtp_auth_code  # 注意：是授权码，不是密码
FROM_EMAIL=your_email@qq.com
FROM_NAME=VerifAIble

# 安全配置
SECRET_KEY=your-secret-key-here
HTTPS=True

# 其他配置
DEBUG=False
```

## Supervisor 配置

如果还没有配置 Supervisor，创建配置文件：

### 1. 创建配置
```bash
sudo vim /etc/supervisor/conf.d/verifaible.conf
```

### 2. 添加配置内容
```ini
[program:verifaible]
command=/path/to/venv/bin/python /path/to/VerifAIble/websocket_server.py
directory=/path/to/VerifAIble
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/verifaible/access.log
stderr_logfile=/var/log/verifaible/error.log
environment=PATH="/path/to/venv/bin"
```

### 3. 创建日志目录
```bash
sudo mkdir -p /var/log/verifaible
sudo chown www-data:www-data /var/log/verifaible
```

### 4. 重新加载配置
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start verifaible
```

## Nginx 配置

### 1. 创建配置文件
```bash
sudo vim /etc/nginx/sites-available/verifaible.space
```

### 2. 添加配置
```nginx
server {
    listen 80;
    server_name verifaible.space;

    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name verifaible.space;

    # SSL 证书（由 Let's Encrypt 生成）
    ssl_certificate /etc/letsencrypt/live/verifaible.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/verifaible.space/privkey.pem;

    # 反向代理到 Flask 应用
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置（浏览器任务可能耗时较长）
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }

    # 静态文件（下载的PDF等）
    location /downloads/ {
        alias /path/to/VerifAIble/downloads/;
        # 可以添加认证保护
        # auth_basic "Restricted";
        # auth_basic_user_file /etc/nginx/.htpasswd;
    }

    location /task_data/ {
        alias /path/to/VerifAIble/task_data/;
    }

    # 日志
    access_log /var/log/nginx/verifaible_access.log;
    error_log /var/log/nginx/verifaible_error.log;
}
```

### 3. 启用站点
```bash
sudo ln -s /etc/nginx/sites-available/verifaible.space /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. 配置 HTTPS（Let's Encrypt）
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d verifaible.space
```

## 监控和维护

### 查看服务状态
```bash
sudo supervisorctl status verifaible
```

### 查看实时日志
```bash
# Supervisor 日志
tail -f /var/log/verifaible/error.log

# Nginx 日志
tail -f /var/log/nginx/verifaible_error.log
```

### 查看任务执行情况
```bash
sqlite3 verifaible.db "SELECT id, status, query, created_at FROM tasks ORDER BY id DESC LIMIT 10;"
```

### 重启服务
```bash
sudo supervisorctl restart verifaible
```

### 停止服务
```bash
sudo supervisorctl stop verifaible
```

## 定期维护

### 1. 清理旧文件（添加到 crontab）
```bash
crontab -e
```

添加：
```cron
# 每天凌晨2点清理7天前的下载文件
0 2 * * * find /path/to/VerifAIble/downloads -type f -mtime +7 -delete

# 每周清理30天前的任务报告
0 3 * * 0 find /path/to/VerifAIble/task_data/reports -type f -mtime +30 -delete

# 每天备份数据库
0 4 * * * cp /path/to/VerifAIble/verifaible.db /path/to/backups/verifaible_$(date +\%Y\%m\%d).db
```

### 2. 优化数据库
```bash
# 每月运行一次
sqlite3 verifaible.db "VACUUM;"
```

### 3. 检查磁盘空间
```bash
df -h
du -sh downloads/ task_data/
```

## 回滚部署

如果部署出现问题，可以回滚：

```bash
# 1. 恢复数据库
cp backups/verifaible_YYYYMMDD_HHMMSS.db verifaible.db

# 2. 回滚代码
git log --oneline  # 查看提交历史
git reset --hard <commit-hash>

# 3. 重启服务
sudo supervisorctl restart verifaible
```

## 故障排查

### 服务无法启动
```bash
# 查看详细错误
sudo supervisorctl tail -f verifaible stderr

# 检查端口占用
sudo lsof -i :3001

# 手动启动测试
cd /path/to/VerifAIble
source venv/bin/activate
python websocket_server.py
```

### 邮件发送失败
```bash
# 测试邮件服务
python test_email_only.py

# 检查 SMTP 配置
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(f'SMTP: {os.getenv(\"SMTP_HOST\")}:{os.getenv(\"SMTP_PORT\")}')"
```

### 浏览器启动失败
```bash
# 重新安装 Playwright
playwright install --with-deps chromium

# 测试浏览器
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); print('OK')"
```

## 安全检查清单

- [ ] `.env` 文件权限设置为 600
- [ ] 数据库文件权限正确
- [ ] Nginx 配置了 HTTPS
- [ ] 静态文件目录有访问控制
- [ ] Supervisor 使用非 root 用户运行
- [ ] 防火墙只开放必要端口（80, 443）
- [ ] 定期备份数据库
- [ ] 日志定期清理

## 性能优化建议

### 1. 使用 Gunicorn（多进程）
修改 Supervisor 配置：
```ini
command=/path/to/venv/bin/gunicorn -w 4 -b 127.0.0.1:3001 websocket_server:app
```

### 2. Redis 缓存（可选）
```bash
sudo apt install redis-server
pip install redis
```

### 3. 任务队列限制
在代码中添加并发限制，避免同时执行太多任务。

---

**需要帮助？** 查看完整文档：`BROWSER_AGENT_DEPLOYMENT.md`
