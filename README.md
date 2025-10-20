# UniAgent - AI语音助手

欧阳宁秀AI语音助手 - 基于OpenAI Realtime API的智能语音对话系统，集成意图识别功能。

## 功能特性

- **实时语音对话**: 使用OpenAI Realtime API实现低延迟语音交互
- **意图识别**: 集成PyTorch CNN+GRU+Attention模型，智能识别用户查询意图
- **Google OAuth登录**: 安全的用户认证系统
- **对话历史**: 保存用户对话记录和工具调用历史
- **多用户支持**: 每个用户使用自己的OpenAI API密钥
- **响应式设计**: 支持桌面和移动设备访问
- **PWA支持**: 可添加到手机主屏幕，类似原生应用

## 技术栈

### 后端
- **Flask**: Python Web框架
- **SQLAlchemy**: ORM数据库操作
- **Authlib**: Google OAuth 2.0认证
- **PyTorch**: 意图识别模型推理
- **Gunicorn**: 生产级WSGI服务器

### 前端
- 原生JavaScript + WebSocket
- iPhone风格UI设计
- 实时音频处理 (Web Audio API)

### 数据库
- 开发环境: SQLite
- 生产环境: PostgreSQL/MySQL

## 项目结构

```
UniAgent/
├── models.py                 # 数据库模型定义
├── auth.py                   # Google OAuth认证模块
├── websocket_server.py       # 主服务器 (生产环境)
├── intent_api.py            # 意图识别API
├── intent_classifier.py     # 意图识别模型
├── init_db.py              # 数据库初始化脚本
├── static/
│   ├── websocket.html      # 主界面 (语音对话)
│   ├── login.html          # 登录页面
│   └── settings.html       # 设置页面
├── requirements.txt         # Python依赖
├── gunicorn_config.py      # Gunicorn配置
├── nginx.conf              # Nginx配置示例
├── .env.example            # 环境变量模板
├── DEPLOYMENT.md           # 部署指南
└── README.md               # 本文件
```

## 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/your-username/UniAgent.git
cd UniAgent

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下内容:

```bash
# Flask配置
SECRET_KEY=your-secret-key-here
DEBUG=True
HTTPS=False

# 数据库配置 (开发环境使用SQLite)
DATABASE_URL=sqlite:///uniagent.db

# Google OAuth配置
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# 加密密钥
ENCRYPTION_KEY=your-encryption-key-here

# 端口配置
PORT=3001
```

**生成密钥:**

```bash
# 生成SECRET_KEY
python -c "import os; print(os.urandom(24).hex())"

# 生成ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. 配置Google OAuth

参考 [DEPLOYMENT.md](DEPLOYMENT.md#google-oauth配置) 中的详细步骤。

简要步骤:
1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建项目并配置OAuth同意屏幕
3. 创建OAuth 2.0客户端ID
4. 设置回调URL: `http://localhost:3001/auth/callback`
5. 将Client ID和Secret配置到 `.env` 文件

### 4. 初始化数据库

```bash
python init_db.py
```

### 5. 启动服务器

```bash
python websocket_server.py
```

访问: http://localhost:3001

## 使用流程

### 首次使用

1. **登录**: 使用Google账号登录
2. **配置API密钥**: 在设置页面输入您的OpenAI API密钥
3. **开始对话**: 点击绿色接听按钮，开始与AI语音对话

### 意图识别示例

尝试说以下内容:

- "我想学Python"
- "贵州茅台股票"
- "比特币价格"
- "个人所得税计算器"

AI会自动调用意图识别工具，推荐相关网站。

## 架构说明

### 1. 认证流程

```
用户 → Google OAuth → 服务器验证 → 创建/更新用户 → 登录成功
```

### 2. 语音对话流程

```
用户说话 → 浏览器录音 → WebSocket发送 → OpenAI Realtime API
                ↓
            意图识别工具调用
                ↓
AI回复 ← OpenAI生成音频 ← 服务器处理 ← 工具返回结果
```

### 3. 数据存储

- **users**: 用户基本信息和加密的API密钥
- **conversations**: 对话会话记录
- **messages**: 对话消息内容（转录文本）
- **tool_calls**: 工具调用记录

## API端点

### 认证相关
- `GET /login` - 登录页面
- `GET /auth/login` - 开始Google OAuth流程
- `GET /auth/callback` - OAuth回调
- `GET /auth/logout` - 退出登录
- `GET /auth/user/info` - 获取用户信息
- `GET/POST /auth/user/api-key` - 管理API密钥

### 对话相关
- `GET /` - 主页面（语音对话界面）
- `GET /settings` - 设置页面
- `GET /api_key` - 获取用户API密钥
- `POST /conversation/start` - 开始新对话
- `POST /conversation/end` - 结束对话
- `POST /conversation/message` - 保存消息
- `GET /conversation/history` - 获取对话历史

### 工具相关
- `POST /recognize_intent` - 意图识别

## 部署到生产环境

详细部署步骤请参考 [DEPLOYMENT.md](DEPLOYMENT.md)

### 快速部署清单

- [ ] 购买域名并配置DNS
- [ ] 租用云服务器（推荐2核4G）
- [ ] 配置Google OAuth生产环境回调URL
- [ ] 安装PostgreSQL/MySQL数据库
- [ ] 配置Nginx反向代理
- [ ] 使用Let's Encrypt配置SSL证书
- [ ] 使用Gunicorn + Systemd运行服务
- [ ] 配置防火墙和安全策略
- [ ] 设置数据库备份

## 移动端访问

### PWA方式（推荐）

用户可以直接通过浏览器访问，并添加到主屏幕:

**iOS:**
1. 使用Safari打开网站
2. 点击"分享" → "添加到主屏幕"

**Android:**
1. 使用Chrome打开网站
2. 点击菜单 → "添加到主屏幕"

### 原生应用（可选）

如需开发原生应用，可使用WebView封装:
- iOS: Swift + WKWebView
- Android: Kotlin + WebView

## 开发指南

### 添加新的意图识别类别

1. 更新训练数据: `training_data_v2.json`
2. 更新类别映射: `category_map.json`
3. 更新URL配置: `url_config.json`
4. 重新训练模型: `python train_with_new_data.py`

### 自定义UI

主界面样式在 `static/websocket.html` 中定义，使用CSS变量可快速调整:

```css
body::before {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

### 添加新的工具

1. 在 `websocket_server.py` 中定义工具函数
2. 在 `static/websocket.html` 的session配置中注册工具
3. 处理工具调用事件

## 故障排查

### WebSocket连接失败

- 检查API密钥是否正确配置
- 查看浏览器控制台错误信息
- 确认网络可访问OpenAI API

### 音频播放问题

- 确认浏览器权限已授予麦克风访问
- 检查音频格式配置（PCM16, 24kHz）
- 查看控制台是否有音频解码错误

### 数据库错误

- 确认DATABASE_URL配置正确
- 检查数据库连接权限
- 运行 `python init_db.py` 重新初始化

## 性能优化

- 使用CDN加速静态资源
- 配置Nginx缓存
- 使用Redis缓存会话
- 数据库连接池优化
- 启用Gzip压缩

## 安全建议

- 定期更新依赖包
- 使用强密码和密钥
- 启用HTTPS
- 配置CORS策略
- 实施访问频率限制
- 定期备份数据库

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

- GitHub: [your-username](https://github.com/your-username)
- Email: your-email@example.com

## 致谢

- OpenAI Realtime API
- Flask Web Framework
- PyTorch Deep Learning Library
- Google OAuth 2.0

---

**欧阳宁秀AI语音助手** - 让语音交互更智能 🎤✨