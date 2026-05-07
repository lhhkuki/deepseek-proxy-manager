# AI Proxy Manager

<div align="center">

将 ChatGPT Codex Desktop 的 API 请求中转至第三方 LLM 供应商。

**DeepSeek · Kimi Code · Moonshot — 无需 VPN，按需付费**

<p>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Frontend-React_+_Electron-61DAFB?style=flat-square&logo=react&logoColor=white" alt="React">
  <img src="https://img.shields.io/badge/Protocol-OpenAI_+_Anthropic-412991?style=flat-square" alt="Protocol">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows&logoColor=white" alt="Windows">
</p>

[快速开始](#-快速开始) · [可用供应商](#-支持的供应商) · [配置说明](#-配置-codex) · [项目结构](#-项目结构)

</div>

---

## 为什么需要

Codex Desktop 原生只支持 OpenAI API，且默认连接 `api.openai.com`（需要 VPN）。

AI Proxy Manager 在本地运行一个轻量代理，将 Codex 的 API 请求自动翻译为各供应商的协议格式：

```
Codex (Responses API) → 127.0.0.1:15800 → DeepSeek / Kimi / Moonshot
```

- **省钱** — DeepSeek、Kimi Code 按月套餐比 OpenAI 按量计费便宜
- **免 VPN** — 国内供应商直连
- **无感切换** — 填什么地址自动适配协议，不用改 Codex 任何设置

## 功能

- 多供应商支持 — DeepSeek / Kimi Code / Moonshot
- 协议自动检测 — OpenAI Chat Completions / Anthropic Messages 自动切换
- 模型管理 — 添加、编辑、删除模型，每个模型独立配置 API 地址和密钥
- 推理开关 — 每个模型可独立开启/关闭推理增强
- 实时日志 — 查看每一条请求的转发状态
- 系统托盘 — 最小化到托盘，开机自启
- Electron 桌面应用 — 美观的现代化 UI
- 单文件打包 — 可分发为独立 .exe

## 快速开始

### 1. 准备

- 安装 [Codex Desktop](https://codex.openai.com)
- 准备一个第三方 API Key（[DeepSeek](https://platform.deepseek.com) / [Kimi Code](https://www.kimi.com/code) / [Moonshot](https://platform.moonshot.cn)）

### 2. 启动

```bash
# 方式一：双击启动器（Windows）
启动代理.bat

# 方式二：命令行
pip install -r requirements.txt
python proxy_manager.py
```

### 3. 配置 Codex

编辑 `~/.codex/config.toml`：

```toml
model_provider = "custom"
model = "deepseek-v4-pro"

[model_providers]
[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "http://127.0.0.1:15800/v1"
```

### 4. 添加模型

打开前端界面（系统托盘或浏览器访问 `http://127.0.0.1:15801`），在"模型"标签页添加你的 API 配置。

## 支持的供应商

| 供应商 | base_url | 协议 | 推理支持 |
|--------|----------|------|----------|
| DeepSeek | `https://api.deepseek.com` | OpenAI Chat Completions | ✅ |
| Kimi Code | `https://api.kimi.com/coding/v1` | Anthropic Messages | ✅ |
| Moonshot | `https://api.moonshot.cn/v1` | OpenAI Chat Completions | ✅ |

代理自动检测 Kimi Code 地址，切换为 Anthropic Messages 协议。

## 项目结构

```
deepseek-proxy-manager/
├── proxy_manager.py              ← 后端启动器（代理 + API）
├── api_server.py                 ← Flask REST API
├── requirements.txt
├── 启动代理.bat
├── proxy/
│   ├── config.py                 ← 配置、API Key 加密、推理缓存
│   ├── server.py                 ← HTTP 代理服务器
│   ├── handler.py                ← 请求路由 + 通用方法
│   ├── translate_openai.py       ← Responses → Chat Completions 翻译
│   └── translate_anthropic.py    ← Responses → Anthropic Messages 翻译
├── gui/
│   └── app.py                    ← tkinter 托盘 GUI（旧版，已被前端替代）
└── frontend/
    ├── src/                      ← React + TypeScript 前端
    ├── electron/                 ← Electron 主进程
    └── package.json
```

## 技术要点

| 事项 | 说明 |
|------|------|
| 协议转换 | OpenAI Responses API → Chat Completions / Anthropic Messages |
| 推理缓存 | 多轮对话的 reasoning_content / thinking 缓存与注入 |
| 模型映射 | Codex 子代理的 gpt-5.4 等模型名自动映射到配置模型 |
| 流式转发 | SSE 流式响应实时翻译（OpenAI / Anthropic 双向） |
| 工具调用 | function_call / tool_use 格式在两个协议间互转 |
| 孤儿清理 | 未配对 tool_use/tool_result 自动邻接匹配清理 |
| 图片传输 | data URI → base64 / URL 源，保留图像数据 |
| API Key | XOR 加密存储，机器绑定 |

## 打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "DeepSeek-Proxy-Manager" proxy_manager.py
```

## 许可

仅供个人学习与研究使用。
