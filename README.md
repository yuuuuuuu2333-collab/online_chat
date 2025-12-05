# 在线聊天应用

这是一个基于 Flask-SocketIO 构建的实时在线聊天应用，集成了多种特色功能，包括电影搜索与播放、AI 助手（川小农）、聊天历史记录、移动端自适应以及美观的界面。

## 功能特性

-   **实时聊天**：用户可以加入聊天室进行实时消息交流。
-   **用户管理**：显示在线用户列表，支持昵称唯一性检查。
-   **聊天历史**：自动加载最近的聊天记录。
-   **清空历史记录**：提供清空所有聊天历史记录并释放数据库的选项。
-   **@电影功能**：
    -   支持 `@电影 URL` 直接播放指定视频链接。
    -   支持 `@电影 电影名` 搜索电影并生成播放 iframe。
    -   集成了第三方网站进行视频解析和播放。
-   **@川小农 AI 助手**：
    -   基于 Qwen/Qwen2.5-7B-Instruct 模型（通过 SiliconFlow 的 OpenAI 兼容 API 调用）。
    -   专属四川农业大学助手，专注于回答川农相关问题。
    -   对其他大学的问题会委婉拒绝并引导回川农话题。
    -   支持生成活动通知。
-   **移动端自适应**：界面在手机等小屏幕设备上能良好显示，侧边栏支持展开和关闭。
-   **Telegram 风格背景**：聊天界面背景美观，类似 Telegram 风格。
-   **消息卡片阴影**：消息气泡具有柔和的阴影效果，提升视觉体验。
-   **表情符号支持**：支持在聊天中插入表情符号。

## 技术栈

-   **后端**：Python, Flask, Flask-SocketIO, SQLite, requests, BeautifulSoup4
-   **前端**：HTML, CSS, JavaScript, Socket.IO 客户端
-   **AI**：Qwen/Qwen2.5-7B-Instruct (通过 SiliconFlow 的 OpenAI 兼容 API)

## 安装与运行

### 1. 克隆仓库

```bash
git clone [你的仓库地址]
cd online_chat
```

### 2. 创建并激活虚拟环境

```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置 AI API Key (可选)

如果你想使用 `@川小农` AI 助手功能，你需要设置 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。默认配置如下：

-   `OPENAI_API_KEY`: `sk-rgijapfapkddnnbbwftgcqycdniodxuxqibiwrtfnthxdaqw` (请替换为你的实际 API Key)
-   `OPENAI_BASE_URL`: `https://api.siliconflow.cn/v1`

你可以通过环境变量设置，或者直接修改 `app.py` 中的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 变量。

### 5. 运行应用

```bash
python app.py
```

应用将在 `http://0.0.0.0:5000` 启动。在浏览器中访问 `http://localhost:5000` 即可使用。

## 使用指南

1.  **登录**：输入你的昵称进入聊天室。
2.  **发送消息**：在输入框中输入消息，按 Enter 键发送。
3.  **@电影功能**：
    -   发送 `@电影 [视频URL]`：直接播放指定 URL 的视频。
4.  **@川小农 AI 助手**：
    -   发送 `@川小农 [你的问题]`：与 AI 助手对话，提问关于四川农业大学的问题。
    -   发送 `@川小农 生成活动通知 主题：xxx 时间：xxx 地点：xxx`：生成活动通知。
5.  **清空历史记录**：点击侧边栏的“Clear History”按钮，可以清空所有聊天记录。
6.  **移动端**：在手机浏览器中访问，界面会自动适应。点击左上角的菜单按钮可以展开/关闭用户列表。

## 文件结构

```
.
├── app.py                  # Flask 后端应用主文件
├── chat.db                 # SQLite 数据库文件 (存储聊天记录和用户信息)
├── requirements.txt        # Python 依赖列表
├── static/
│   ├── css/
│   │   └── chat.css        # 样式文件
│   ├── js/
│   │   └── chat.js         # 前端 JavaScript 逻辑
│   └── images/             # 存放图片资源 (如果需要)
└── templates/
    ├── chat.html           # 聊天室页面模板
    └── login.html          # 登录页面模板
```

## 注意事项

-   `@电影` 功能依赖于第三方视频解析服务 `jx.playerjy.com` 和 `libvio.link` 网站，其可用性可能受外部因素影响。
-   `@川小农` 功能依赖于 SiliconFlow 提供的 OpenAI 兼容 API，请确保你的 API Key 有效且网络连接正常。
-   本应用仅用于学习和演示目的，未进行生产环境优化和安全加固。

