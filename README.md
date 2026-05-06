# DeepSeek Proxy Manager

让 [Codex](https://github.com/openai/codex) 通过 DeepSeek API 进行对话的本地代理工具，带图形化管理界面。

## 为什么需要它？

Codex 使用 OpenAI 的 API 格式（Responses API），但 DeepSeek 的 API 格式不兼容。这个代理在本地做翻译：

```
Codex (Responses API)  →  127.0.0.1:15800  →  DeepSeek (Chat Completions API)
```

同时因为 DeepSeek 国内版不需要 VPN，比直接用 OpenAI API 更稳定便宜。

## 功能

- 启动/停止代理服务器（单文件，含 GUI）
- 设置 DeepSeek API Key、端口、API 地址
- 添加/切换模型
- 实时请求日志
- 系统托盘驻留
- 开机自启
- 一键打包为独立 .exe

## 安装与使用

### 预备条件

- 安装 [Codex](https://github.com/openai/codex) 编辑器
- 准备一个 [DeepSeek API Key](https://platform.deepseek.com/)（需要充值）

### 方式一：直接运行 Python 脚本

```bash
pip install pystray pillow
python proxy_manager.py
```

### 方式二：打包为 exe（发给别人用）

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "DeepSeek-Proxy-Manager" proxy_manager.py
# 输出在 dist/DeepSeek-Proxy-Manager.exe
```

## 配置 Codex

编辑 `~/.codex/config.toml`，写入以下内容：

```toml
model_provider = "custom"
model = "deepseek-v4-pro"

model_context_window = 1000000
model_auto_compact_token_limit = 900000

[model_providers]
[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "http://127.0.0.1:15800/v1"
```

## 使用步骤

1. 双击运行 `DeepSeek-Proxy-Manager.exe`，系统托盘出现蓝色图标
2. 右键托盘 → **显示** 打开窗口
3. 在 **设置** 标签页填入 DeepSeek API Key（sk- 开头），点击 **保存设置**
4. 点击 **启动**，状态灯变为绿色
5. 打开 Codex，正常对话

## 常见问题

### Codex 报 404 Not Found

`base_url` 没配对。检查 Codex 的 `config.toml` 中 `base_url` 是否写的是 `http://127.0.0.1:15800/v1`，不要直连 DeepSeek。

### Codex 报连接错误

代理未启动。确认代理窗口状态灯是绿色的。

### 代理启动失败

端口 15800 被占用。检查是否已经运行了一个代理实例，或关闭占用端口的程序。

### DeepSeek V4 Pro 后续对话异常

V4 Pro 是推理模型，需要缓存 `reasoning_content`。代理已内置该逻辑，正常情况下无需额外配置。

## 项目结构

```
deepseek-proxy-manager/
├── proxy_manager.py             ← 入口（30行）
├── requirements.txt
├── 启动代理.bat
├── proxy/
│   ├── config.py                ← 配置、常量、缓存
│   ├── server.py                ← 代理服务器线程
│   ├── handler.py               ← HTTP 路由 + 通用方法
│   ├── translate_openai.py      ← OpenAI 格式翻译
│   └── translate_anthropic.py   ← Anthropic 格式翻译
└── gui/
    └── app.py                   ← 托盘 GUI
```

## 支持的上游

| 服务 | base_url | 格式 |
|------|------|------|
| DeepSeek | `https://api.deepseek.com` | OpenAI Chat Completions |
| Kimi Code | `https://api.kimi.com/coding/v1` | Anthropic Messages（自动检测） |
| Moonshot | `https://api.moonshot.cn/v1` | OpenAI Chat Completions |

## 技术要点

| 事项 | 说明 |
|------|------|
| 协议转换 | OpenAI Responses API → DeepSeek Chat Completions API |
| 推理缓存 | V4 Pro 的 reasoning_content 跨轮次缓存/注入 |
| 模型映射 | Codex 子代理的 gpt-5.4 等模型名自动映射到 DeepSeek |
| 流式转发 | 支持 SSE 流式响应，实时文字输出 |
| 工具调用 | function_call 格式在两个协议间互转 |
