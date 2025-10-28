#!/bin/bash
# VerifAIble 服务器部署脚本
# 用法: bash deploy_to_server.sh

set -e  # 遇到错误立即退出

echo "======================================================================"
echo "VerifAIble 服务器部署脚本"
echo "======================================================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在项目目录
if [ ! -f "websocket_server.py" ]; then
    echo -e "${RED}❌ 错误: 请在 VerifAIble 项目根目录下运行此脚本${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/8] 备份当前数据...${NC}"
# 备份数据库
if [ -f "verifaible.db" ]; then
    BACKUP_DIR="backups"
    mkdir -p $BACKUP_DIR
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    cp verifaible.db "$BACKUP_DIR/verifaible_$TIMESTAMP.db"
    echo -e "${GREEN}✓ 数据库已备份到: $BACKUP_DIR/verifaible_$TIMESTAMP.db${NC}"
else
    echo -e "${YELLOW}⚠️  数据库文件不存在，跳过备份${NC}"
fi

# 备份 .env 文件
if [ -f ".env" ]; then
    cp .env .env.backup
    echo -e "${GREEN}✓ 环境变量已备份到: .env.backup${NC}"
fi

echo ""
echo -e "${YELLOW}[2/8] 拉取最新代码...${NC}"
# 保存本地修改（如果有）
git stash push -m "Auto stash before deployment $(date +%Y%m%d_%H%M%S)"

# 拉取最新代码
git pull origin main || {
    echo -e "${RED}❌ Git pull 失败${NC}"
    echo -e "${YELLOW}💡 尝试强制拉取...${NC}"
    git fetch --all
    git reset --hard origin/main
}

# 恢复 .env 文件（如果被覆盖）
if [ -f ".env.backup" ]; then
    if [ ! -f ".env" ] || [ ".env" -ot ".env.backup" ]; then
        cp .env.backup .env
        echo -e "${GREEN}✓ 环境变量文件已恢复${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}[3/8] 激活虚拟环境...${NC}"
# 检查虚拟环境
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${GREEN}✓ 虚拟环境已激活${NC}"
elif [ -d "VerifAIble" ]; then
    source VerifAIble/bin/activate
    echo -e "${GREEN}✓ 虚拟环境已激活${NC}"
else
    echo -e "${RED}❌ 未找到虚拟环境${NC}"
    echo -e "${YELLOW}💡 创建虚拟环境: python -m venv venv${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}[4/8] 更新依赖...${NC}"
pip install -r requirements.txt --quiet
echo -e "${GREEN}✓ Python 依赖已更新${NC}"

# 检查 Playwright
if ! playwright --version &> /dev/null; then
    echo -e "${YELLOW}💡 安装 Playwright 浏览器...${NC}"
    playwright install chromium
fi

echo ""
echo -e "${YELLOW}[5/8] 运行数据库迁移...${NC}"
# 检查是否需要运行迁移
if [ -f "migrate_add_downloaded_files.py" ]; then
    python migrate_add_downloaded_files.py
    echo -e "${GREEN}✓ 数据库迁移完成${NC}"
else
    echo -e "${YELLOW}⚠️  未找到迁移脚本，跳过${NC}"
fi

echo ""
echo -e "${YELLOW}[6/8] 运行部署检查...${NC}"
if [ -f "check_deployment.py" ]; then
    python check_deployment.py
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ 部署检查通过${NC}"
    else
        echo -e "${RED}❌ 部署检查失败，请修复上述问题后重试${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  未找到检查脚本，跳过${NC}"
fi

echo ""
echo -e "${YELLOW}[7/8] 创建必要的目录...${NC}"
mkdir -p downloads task_data/reports logs backups
echo -e "${GREEN}✓ 目录结构已就绪${NC}"

echo ""
echo -e "${YELLOW}[8/8] 重启服务...${NC}"

# 检查是否使用 Supervisor 管理
if command -v supervisorctl &> /dev/null; then
    echo -e "${YELLOW}检测到 Supervisor，正在重启服务...${NC}"
    sudo supervisorctl restart verifaible

    # 等待服务启动
    sleep 2

    # 检查服务状态
    STATUS=$(sudo supervisorctl status verifaible)
    if echo "$STATUS" | grep -q "RUNNING"; then
        echo -e "${GREEN}✓ 服务已重启并运行中${NC}"
    else
        echo -e "${RED}❌ 服务启动失败${NC}"
        echo "$STATUS"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  未检测到 Supervisor${NC}"
    echo -e "${YELLOW}💡 请手动重启服务，或使用以下命令:${NC}"
    echo "   pkill -f websocket_server.py"
    echo "   nohup python websocket_server.py > logs/server.log 2>&1 &"
fi

echo ""
echo "======================================================================"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "======================================================================"
echo ""
echo "📋 部署信息:"
echo "   - 备份目录: backups/"
echo "   - 日志目录: logs/"
echo "   - 下载目录: downloads/"
echo ""
echo "🔍 检查服务状态:"
echo "   sudo supervisorctl status verifaible"
echo ""
echo "📄 查看日志:"
echo "   tail -f /var/log/verifaible/error.log"
echo "   # 或"
echo "   tail -f logs/server.log"
echo ""
echo "🌐 访问服务:"
echo "   https://verifaible.space"
echo ""
