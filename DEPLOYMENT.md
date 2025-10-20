# 部署指南

本文档介绍如何将UniAgent AI语音助手部署到生产服务器。

## 目录
1. [前置准备](#前置准备)
2. [Google OAuth配置](#google-oauth配置)
3. [服务器配置](#服务器配置)
4. [部署步骤](#部署步骤)
5. [SSL证书配置](#ssl证书配置)
6. [移动端访问](#移动端访问)

---

## 前置准备

### 1. 域名
- 购买并配置域名（如: uniagent.com）
- 将域名A记录指向服务器IP地址

### 2. 云服务器
推荐配置:
- CPU: 2核或以上
- 内存: 4GB或以上
- 存储: 20GB或以上
- 操作系统: Ubuntu 22.04 LTS

### 3. 必需软件
- Python 3.10+
- PostgreSQL 或 MySQL (生产环境推荐)
- Nginx
- Git

---

## Google OAuth配置

### 1. 创建Google Cloud项目

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 项目名称: UniAgent Voice Assistant

### 2. 配置OAuth同意屏幕

1. 导航至: APIs & Services > OAuth consent screen
2. 选择用户类型: **External**
3. 填写应用信息:
   - 应用名称: `欧阳宁秀 AI语音助手`
   - 用户支持电子邮件: 您的邮箱
   - 应用徽标: (可选) 上传头像
   - 应用首页: `https://your-domain.com`
   - 授权域: `your-domain.com`
   - 开发者联系信息: 您的邮箱

4. 作用域: 添加以下作用域
   - `openid`
   - `email`
   - `profile`

### 3. 创建OAuth 2.0客户端ID

1. 导航至: APIs & Services > Credentials
2. 点击 "Create Credentials" > "OAuth client ID"
3. 应用类型: **Web application**
4. 名称: UniAgent Web Client
5. 授权的重定向URI:
   ```
   https://your-domain.com/auth/callback
   ```
6. 点击 "Create"
7. 保存 **Client ID** 和 **Client Secret**

---

## 服务器配置

### 1. 连接服务器

```bash
ssh root@your-server-ip
```

### 2. 安装系统依赖

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装Python和依赖
sudo apt install -y python3.10 python3.10-venv python3-pip

# 安装PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# 安装Nginx
sudo apt install -y nginx

# 安装Git
sudo apt install -y git
```

### 3. 配置PostgreSQL

```bash
# 切换到postgres用户
sudo -u postgres psql

# 创建数据库和用户
CREATE DATABASE uniagent;
CREATE USER uniagent_user WITH PASSWORD 'your-secure-password';
GRANT ALL PRIVILEGES ON DATABASE uniagent TO uniagent_user;
\q
```

---

## 部署步骤

### 1. 克隆代码

```bash
# 创建应用目录
sudo mkdir -p /var/www
cd /var/www

# 克隆仓库
sudo git clone https://github.com/your-username/UniAgent.git
cd UniAgent

# 设置权限
sudo chown -R $USER:$USER /var/www/UniAgent
```

### 2. 创建Python虚拟环境

```bash
python3.10 -m venv venv
source venv/bin/activate
```

### 3. 安装Python依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
cp .env.example .env
nano .env
```

编辑 `.env` 文件:

```bash
# Flask配置
SECRET_KEY=your-generated-secret-key
DEBUG=False
HTTPS=True

# 数据库配置
DATABASE_URL=postgresql://uniagent_user:your-secure-password@localhost:5432/uniagent

# Google OAuth配置
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# 加密密钥
ENCRYPTION_KEY=your-generated-encryption-key

# 端口配置
PORT=3001
```

**生成密钥:**

```bash
# 生成SECRET_KEY
python3 -c "import os; print(os.urandom(24).hex())"

# 生成ENCRYPTION_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5. 初始化数据库

```bash
python init_db.py
```

### 6. 测试应用

```bash
python websocket_server.py
```

访问 `http://your-server-ip:3001` 测试是否正常运行。

按 `Ctrl+C` 停止测试。

### 7. 配置Systemd服务

创建服务文件:

```bash
sudo nano /etc/systemd/system/uniagent.service
```

内容:

```ini
[Unit]
Description=UniAgent Voice Assistant
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=/var/www/UniAgent
Environment="PATH=/var/www/UniAgent/venv/bin"
ExecStart=/var/www/UniAgent/venv/bin/gunicorn -c gunicorn_config.py websocket_server:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务:

```bash
sudo systemctl daemon-reload
sudo systemctl start uniagent
sudo systemctl enable uniagent
sudo systemctl status uniagent
```

### 8. 配置Nginx

```bash
sudo nano /etc/nginx/sites-available/uniagent
```

将 `nginx.conf` 文件内容复制到这里，并修改:
- `your-domain.com` 改为您的实际域名
- `/path/to/UniAgent` 改为 `/var/www/UniAgent`

创建软链接:

```bash
sudo ln -s /etc/nginx/sites-available/uniagent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## SSL证书配置

### 使用Let's Encrypt (免费)

```bash
# 安装Certbot
sudo apt install -y certbot python3-certbot-nginx

# 获取SSL证书
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# 测试自动续期
sudo certbot renew --dry-run
```

证书会自动续期，无需手动操作。

### 更新Nginx配置

Certbot会自动修改Nginx配置。验证:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## 移动端访问

### 方式1: 渐进式Web应用 (PWA)

用户可以直接通过手机浏览器访问您的网站:

1. 访问 `https://your-domain.com`
2. 使用Google账号登录
3. 配置OpenAI API密钥
4. 开始使用语音助手

**添加到主屏幕 (类似原生应用):**

- **iOS**: Safari > 分享 > 添加到主屏幕
- **Android**: Chrome > 菜单 > 添加到主屏幕

### 方式2: 开发原生应用 (可选)

如果需要原生应用:

1. **iOS**: 使用Swift + WebView封装
2. **Android**: 使用Kotlin + WebView封装

原生应用可以提供:
- 更好的性能
- 离线支持
- 推送通知
- 更深度的系统集成

---

## 维护和监控

### 查看日志

```bash
# 应用日志
sudo journalctl -u uniagent -f

# Nginx访问日志
sudo tail -f /var/log/nginx/uniagent_access.log

# Nginx错误日志
sudo tail -f /var/log/nginx/uniagent_error.log
```

### 重启服务

```bash
# 重启应用
sudo systemctl restart uniagent

# 重启Nginx
sudo systemctl restart nginx
```

### 更新代码

```bash
cd /var/www/UniAgent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart uniagent
```

### 数据库备份

```bash
# 备份PostgreSQL数据库
pg_dump -U uniagent_user uniagent > backup_$(date +%Y%m%d).sql

# 恢复数据库
psql -U uniagent_user uniagent < backup_YYYYMMDD.sql
```

---

## 安全建议

1. **防火墙配置**
   ```bash
   sudo ufw allow 22/tcp      # SSH
   sudo ufw allow 80/tcp      # HTTP
   sudo ufw allow 443/tcp     # HTTPS
   sudo ufw enable
   ```

2. **定期更新系统**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

3. **配置fail2ban防止暴力破解**
   ```bash
   sudo apt install -y fail2ban
   sudo systemctl enable fail2ban
   ```

4. **定期备份数据库和用户数据**

5. **使用强密码和密钥**

---

## 故障排查

### 服务无法启动

```bash
# 查看详细日志
sudo journalctl -u uniagent -xe

# 检查端口占用
sudo lsof -i :3001
```

### WebSocket连接失败

- 确认Nginx配置正确支持WebSocket
- 检查防火墙规则
- 查看浏览器控制台错误

### 数据库连接失败

- 验证DATABASE_URL配置
- 检查PostgreSQL服务状态: `sudo systemctl status postgresql`
- 确认数据库用户权限

---

## 联系支持

如有问题，请:
- 查看日志文件
- 搜索GitHub Issues
- 提交新Issue

---

## 总结

完成以上步骤后，您的UniAgent AI语音助手将:

- ✅ 运行在生产服务器上
- ✅ 通过HTTPS安全访问
- ✅ 支持Google账号登录
- ✅ 保存用户对话历史
- ✅ 可通过移动设备访问
- ✅ 自动SSL证书续期

您的用户可以通过浏览器或PWA方式在任何设备上使用您的AI语音助手服务!
