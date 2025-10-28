# 🚀 部署前检查清单

## 本地准备

### 代码提交
- [ ] 所有代码已提交到 Git
- [ ] 代码已推送到 main 分支
- [ ] 确认 `.gitignore` 正确配置（不包含 `.env` 等敏感文件）

```bash
git add .
git commit -m "Deploy BrowserAgent & EmailAgent integration"
git push origin main
```

### 文件检查
- [ ] `requirements.txt` 包含所有依赖
- [ ] `.env.example` 已更新（示例配置）
- [ ] 部署脚本有执行权限（`deploy_to_server.sh`）
- [ ] 迁移脚本准备好（`migrate_add_downloaded_files.py`）

## 服务器准备

### 系统要求
- [ ] Ubuntu 20.04+ 或 CentOS 8+
- [ ] Python 3.10+
- [ ] Git 已安装
- [ ] 至少 2GB RAM
- [ ] 至少 10GB 可用磁盘空间

### 必要软件
```bash
# 检查并安装
sudo apt update
sudo apt install python3-pip python3-venv git nginx supervisor sqlite3

# 检查版本
python3 --version
git --version
nginx -v
```

### 域名和 SSL
- [ ] 域名 DNS 已指向服务器 IP
- [ ] 80 和 443 端口已开放
- [ ] 准备配置 Let's Encrypt

```bash
# 测试域名解析
ping verifaible.space
```

## 环境配置

### 1. 创建项目目录
```bash
sudo mkdir -p /var/www/verifaible
sudo chown $USER:$USER /var/www/verifaible
cd /var/www/verifaible
```

### 2. 克隆代码
```bash
git clone https://github.com/your-repo/VerifAIble.git .
```

### 3. 创建虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. 配置环境变量
```bash
cp .env.example .env
vim .env
```

**必须配置的变量：**
- [ ] `OPENAI_API_KEY` - OpenAI API 密钥
- [ ] `SMTP_HOST` - SMTP 服务器
- [ ] `SMTP_PORT` - SMTP 端口（587）
- [ ] `SMTP_USER` - SMTP 用户名
- [ ] `SMTP_PASSWORD` - SMTP 授权码（不是邮箱密码！）
- [ ] `FROM_EMAIL` - 发件邮箱
- [ ] `SECRET_KEY` - Flask 密钥（随机生成）
- [ ] `HTTPS=True` - 启用 HTTPS

```bash
# 生成随机密钥
python3 -c "import os; print(os.urandom(24).hex())"
```

### 5. 设置文件权限
```bash
chmod 600 .env
mkdir -p downloads task_data/reports logs backups
chmod 755 downloads task_data logs backups
```

## 首次部署

### 1. 安装依赖
```bash
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. 初始化数据库
```bash
python init_db.py
```

### 3. 运行检查
```bash
python check_deployment.py
```

**必须看到：** ✅ 所有检查通过！

### 4. 配置 Supervisor

创建配置文件：
```bash
sudo vim /etc/supervisor/conf.d/verifaible.conf
```

内容：
```ini
[program:verifaible]
command=/var/www/verifaible/venv/bin/python /var/www/verifaible/websocket_server.py
directory=/var/www/verifaible
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/verifaible/access.log
stderr_logfile=/var/log/verifaible/error.log
environment=PATH="/var/www/verifaible/venv/bin"
```

启动服务：
```bash
sudo mkdir -p /var/log/verifaible
sudo chown www-data:www-data /var/log/verifaible
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start verifaible
```

验证：
```bash
sudo supervisorctl status verifaible
# 应该显示: RUNNING
```

### 5. 配置 Nginx

创建配置：
```bash
sudo vim /etc/nginx/sites-available/verifaible.space
```

内容见 `SERVER_DEPLOYMENT.md`

启用站点：
```bash
sudo ln -s /etc/nginx/sites-available/verifaible.space /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 6. 配置 HTTPS
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d verifaible.space
```

## 后续更新部署

每次更新代码后，只需：

```bash
# 1. SSH 登录服务器
ssh user@verifaible.space

# 2. 进入项目目录
cd /var/www/verifaible

# 3. 运行部署脚本
bash deploy_to_server.sh
```

**脚本会自动：**
1. 备份数据库和配置
2. 拉取最新代码
3. 更新依赖
4. 运行数据库迁移
5. 执行部署检查
6. 重启服务

## 部署验证

### 1. 检查服务状态
```bash
sudo supervisorctl status verifaible
# 应该显示: RUNNING
```

### 2. 检查日志
```bash
tail -f /var/log/verifaible/error.log
# 应该没有严重错误
```

### 3. 测试健康检查接口
```bash
curl https://verifaible.space/health
# 应该返回: {"status":"healthy"}
```

### 4. 测试登录
在浏览器访问：`https://verifaible.space`

### 5. 测试深度搜索功能
登录后，在前端提交一个测试任务

### 6. 检查邮件发送
确认任务完成后能收到邮件通知

## 监控设置

### 日志监控
```bash
# 实时查看错误日志
tail -f /var/log/verifaible/error.log

# 查看 Nginx 日志
tail -f /var/log/nginx/verifaible_error.log
```

### 磁盘空间监控
```bash
# 检查总体空间
df -h

# 检查项目文件大小
du -sh /var/www/verifaible/downloads
du -sh /var/www/verifaible/task_data
```

### 数据库监控
```bash
# 查看任务数量
sqlite3 /var/www/verifaible/verifaible.db "SELECT COUNT(*) FROM tasks;"

# 查看最近任务
sqlite3 /var/www/verifaible/verifaible.db "SELECT id, status, created_at FROM tasks ORDER BY id DESC LIMIT 5;"
```

## 定期维护任务

### 每日
- [ ] 检查服务状态
- [ ] 查看错误日志
- [ ] 备份数据库

### 每周
- [ ] 清理旧的下载文件（7天前）
- [ ] 检查磁盘空间
- [ ] 查看任务统计

### 每月
- [ ] 优化数据库（VACUUM）
- [ ] 清理旧的任务报告（30天前）
- [ ] 更新系统和依赖包
- [ ] SSL 证书续期检查

## 紧急回滚步骤

如果部署出现严重问题：

```bash
# 1. 停止服务
sudo supervisorctl stop verifaible

# 2. 恢复数据库
cp backups/verifaible_YYYYMMDD_HHMMSS.db verifaible.db

# 3. 回滚代码
git log --oneline  # 找到上一个稳定版本的 commit
git reset --hard <commit-hash>

# 4. 重启服务
sudo supervisorctl start verifaible
```

## 故障联系方式

- **技术文档**: 查看项目 `docs/` 目录
- **日志位置**: `/var/log/verifaible/`
- **GitHub Issues**: https://github.com/your-repo/issues

## 部署成功标志

- ✅ 服务状态显示 RUNNING
- ✅ 健康检查接口返回正常
- ✅ 可以正常登录
- ✅ 可以创建和执行任务
- ✅ 邮件通知正常发送
- ✅ 日志中无严重错误

---

**完成以上所有检查后，恭喜你完成了 VerifAIble 的部署！** 🎉
