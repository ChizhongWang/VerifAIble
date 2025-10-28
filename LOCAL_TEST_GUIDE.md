# 本地测试指南

## ✅ 服务器已启动成功！

服务器正在运行：**http://localhost:3001**

---

## 📋 测试步骤

### 1. 访问应用

在浏览器打开：**http://localhost:3001**

这会重定向到登录页面（因为需要 Google OAuth 认证）

### 2. 绕过认证测试 API（开发模式）

由于 Google OAuth 需要配置和回调URL，我们可以直接测试 API 端点：

#### 测试健康检查
```bash
curl http://localhost:3001/health
```

应该返回：
```json
{"status":"healthy","service":"OpenAI Realtime WebSocket Server"}
```

### 3. 测试完整流程（不通过Web界面）

使用我们的测试脚本：

#### 方案 A: 测试 BrowserAgent + EmailAgent 集成
```bash
python test_server_integration.py
```

这会：
1. ✅ 执行浏览器任务（访问深交所网站）
2. ✅ 下载PDF文件
3. ✅ 发送邮件通知（附带PDF）
4. ✅ 显示任务摘要

#### 方案 B: 只测试 BrowserAgent
```bash
python test_browseragent.py
```

这会：
1. ✅ 打开浏览器窗口（有头模式）
2. ✅ 执行任务（可以看到AI的每一步操作）
3. ✅ 下载PDF
4. ✅ 发送邮件

#### 方案 C: 只测试邮件功能
```bash
python test_email_only.py
```

---

## 🌐 通过 API 测试（需要认证）

### 前置条件：需要先登录获取 session cookie

由于应用使用 Google OAuth，直接调用 API 需要有效的 session。

### 可选：创建测试用户（临时解决方案）

为了方便测试，可以临时禁用认证检查：

#### 修改 websocket_server.py

找到 `@app.route('/deep_search', methods=['POST'])` 路由，临时注释掉 `@require_auth` 装饰器：

```python
@app.route('/deep_search', methods=['POST'])
# @require_auth  # 临时注释掉用于测试
def deep_search():
    # ...
    # 临时硬编码一个测试用户ID
    user_id = 1  # 添加这行
    # user_id = session['user_id']  # 注释掉这行
```

然后重启服务器，就可以直接测试 API 了。

### 测试深度搜索任务

```bash
curl -X POST http://localhost:3001/deep_search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "帮我查一下安克创新最新的公告"
  }'
```

应该返回：
```json
{
  "success": true,
  "task_id": 1,
  "target_url": "https://www.szse.cn/...",
  "message": "任务已创建，正在后台执行中..."
}
```

### 查询任务状态

```bash
curl http://localhost:3001/tasks/1
```

---

## 🎯 推荐测试流程

### 最简单的测试（推荐）

直接运行完整集成测试：

```bash
python test_server_integration.py
```

**这会模拟整个服务器流程：**
1. BrowserAgent 执行任务
2. 下载PDF文件
3. EmailAgent 发送邮件
4. 显示数据库保存的内容

**预期结果：**
- ✅ 浏览器任务完成
- ✅ 下载了PDF文件（在 `downloads/` 目录）
- ✅ 收到邮件通知（附带PDF和截图）
- ✅ 控制台显示任务摘要

### 观察浏览器操作（有头模式）

如果想看到AI控制浏览器的过程：

```bash
python test_browseragent.py
```

浏览器窗口会打开，你可以看到：
- 🖱️ AI自动在搜索框输入"安克创新"
- 📄 AI找到最新的公告
- 📥 下载PDF文件
- 📧 发送邮件

---

## 📊 查看结果

### 1. 检查下载的文件
```bash
ls -lh downloads/
```

应该看到下载的PDF文件。

### 2. 检查邮件
登录邮箱：`3135718261@qq.com`

应该收到标题为 **"VerifAIble 任务完成通知"** 的邮件，包含：
- 📋 任务摘要
- 📎 PDF附件
- 🖼️ 截图附件
- 📝 任务报告

### 3. 查看任务报告
```bash
ls -lh task_data/reports/
cat task_data/reports/task_*_subtasks.md
```

### 4. 查看数据库
```bash
sqlite3 verifaible.db "SELECT * FROM tasks;"
```

### 5. 查看服务器日志
在运行服务器的终端中可以看到实时日志。

---

## 🐛 常见问题

### Q1: 服务器启动失败
```bash
# 检查端口是否被占用
lsof -i :3001

# 如果被占用，kill掉
kill -9 <PID>

# 重新启动
python websocket_server.py
```

### Q2: 浏览器任务失败
```bash
# 重新安装 Playwright
playwright install chromium

# 测试浏览器
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); print('OK')"
```

### Q3: 邮件发送失败
```bash
# 测试邮件配置
python test_email_only.py

# 检查 .env 配置
cat .env | grep SMTP
```

### Q4: 数据库错误
```bash
# 删除旧数据库重新创建
rm verifaible.db
python init_db.py

# 运行迁移
python migrate_add_downloaded_files.py
```

---

## 🎬 快速演示视频脚本

如果要录制演示视频，按以下步骤：

1. **启动服务器**
   ```bash
   python websocket_server.py
   ```

2. **运行测试**
   ```bash
   python test_browseragent.py
   ```

3. **观看浏览器自动操作**
   - AI搜索"安克创新"
   - 找到最新公告
   - 下载PDF

4. **查看下载的文件**
   ```bash
   open downloads/
   ```

5. **打开邮箱查看邮件**
   - 登录 QQ 邮箱
   - 查看任务完成通知
   - 打开PDF附件

6. **查看任务报告**
   ```bash
   open task_data/reports/
   ```

---

## 🚀 下一步

测试通过后，就可以部署到服务器了！

参考文档：
- **服务器部署**: `SERVER_DEPLOYMENT.md`
- **快速部署**: `QUICK_START.md`
- **部署检查清单**: `DEPLOYMENT_CHECKLIST.md`

---

## 💡 提示

- 测试时使用 **有头模式** (headless=False) 可以看到浏览器操作
- 每次测试会生成新的任务报告在 `task_data/reports/`
- 下载的文件会保存在 `downloads/` 目录
- 邮件附件包含 PDF、截图和报告

**祝测试顺利！** 🎉
