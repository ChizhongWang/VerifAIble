#!/bin/bash
# UniAgent 一键部署脚本
# 适用于 Ubuntu 22.04

set -e  # 遇到错误立即退出

echo "======================================"
echo "  UniAgent AI 语音助手部署脚本"
echo "======================================"
echo ""

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 用户运行此脚本"
    echo "使用: sudo bash deploy.sh"
    exit 1
fi

echo -e "${GREEN}[1/10] 更新系统...${NC}"
apt update && apt upgrade -y

echo -e "${GREEN}[2/10] 安装基础依赖...${NC}"
apt install -y python3.10 python3.10-venv python3-pip git nginx postgresql postgresql-contrib ufw

echo -e "${GREEN}[3/10] 配置防火墙...${NC}"
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
echo "y" | ufw enable

echo -e "${GREEN}[4/10] 配置PostgreSQL...${NC}"
sudo -u postgres psql -c "CREATE DATABASE uniagent;" 2>/dev/null || echo "数据库已存在"
sudo -u postgres psql -c "CREATE USER uniagent_user WITH PASSWORD 'UniAgent2024!@#';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE uniagent TO uniagent_user;"

echo -e "${GREEN}[5/10] 克隆代码...${NC}"
cd /var/www
if [ -d "UniAgent" ]; then
    echo "代码目录已存在，拉取最新代码..."
    cd UniAgent
    git pull origin main
else
    echo "克隆代码仓库..."
    read -p "请输入 GitHub 仓库 URL: " REPO_URL
    git clone "$REPO_URL" UniAgent
    cd UniAgent
fi

echo -e "${GREEN}[6/10] 创建Python虚拟环境...${NC}"
python3.10 -m venv venv
source venv/bin/activate

echo -e "${GREEN}[7/10] 安装Python依赖...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}[8/10] 配置环境变量...${NC}"
if [ ! -f .env ]; then
    cp .env.example .env

    # 生成随机密钥
    SECRET_KEY=$(python3 -c "import os; print(os.urandom(24).hex())")
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

    # 更新.env文件
    sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
    sed -i "s/ENCRYPTION_KEY=.*/ENCRYPTION_KEY=$ENCRYPTION_KEY/" .env
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql://uniagent_user:UniAgent2024!@#@localhost:5432/uniagent|" .env
    sed -i "s/DEBUG=.*/DEBUG=False/" .env
    sed -i "s/HTTPS=.*/HTTPS=True/" .env

    echo -e "${YELLOW}请编辑 /var/www/UniAgent/.env 文件，配置:${NC}"
    echo "  - GOOGLE_CLIENT_ID"
    echo "  - GOOGLE_CLIENT_SECRET"
    echo ""
    read -p "按回车继续..."
fi

echo -e "${GREEN}[9/10] 初始化数据库...${NC}"
python init_db.py

echo -e "${GREEN}[10/10] 配置Systemd服务...${NC}"
cat > /etc/systemd/system/uniagent.service <<EOF
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
EOF

# 设置文件权限
chown -R www-data:www-data /var/www/UniAgent

# 启动服务
systemctl daemon-reload
systemctl enable uniagent
systemctl start uniagent

echo -e "${GREEN}[完成] 配置Nginx...${NC}"
read -p "请输入您的域名 (例如: verifaible.com): " DOMAIN

cat > /etc/nginx/sites-available/uniagent <<EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # WebSocket支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;

        # 缓冲设置
        proxy_buffering off;
        proxy_request_buffering off;
    }

    location /health {
        proxy_pass http://127.0.0.1:3001;
        access_log off;
    }
}
EOF

ln -sf /etc/nginx/sites-available/uniagent /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "======================================"
echo -e "${GREEN}部署完成!${NC}"
echo "======================================"
echo ""
echo "下一步:"
echo "1. 编辑配置文件: nano /var/www/UniAgent/.env"
echo "   配置 GOOGLE_CLIENT_ID 和 GOOGLE_CLIENT_SECRET"
echo ""
echo "2. 重启服务: systemctl restart uniagent"
echo ""
echo "3. 安装SSL证书:"
echo "   apt install -y certbot python3-certbot-nginx"
echo "   certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo ""
echo "4. 检查服务状态:"
echo "   systemctl status uniagent"
echo "   journalctl -u uniagent -f"
echo ""
echo "5. 访问您的网站: http://$DOMAIN"
echo ""
echo "======================================"
