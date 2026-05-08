# AI Proxy Manager

将 Codex Desktop 的 API 请求中转至第三方 LLM（DeepSeek / Kimi Code / Moonshot）。

**不用 VPN，按量付费，比官方 OpenAI 便宜。**

<p>
  <img src="https://img.shields.io/badge/版本-v2.3.1-blue?style=flat-square" alt="版本">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/前端-Electron_+_React-61DAFB?style=flat-square&logo=react" alt="React">
  <img src="https://img.shields.io/badge/平台-Windows-0078D6?style=flat-square&logo=windows" alt="Windows">
</p>

---

## 下载安装

1. 下载 `AI Proxy Manager Setup 2.4.0.exe`
2. 双击安装，选择安装路径
3. 安装完成后打开桌面快捷方式

**不需要装 Python**，所有依赖已打包在内。

---

## 配置 API

打开前端界面（安装后自动弹出），在左侧"模型"标签页：

1. 点击 **添加模型**，填写：
   - 模型 ID（必须填供应商支持的模型名，见下表）
   - 显示名称（随意）
   - API 地址（见下表）
   - API Key（去对应平台申请）
2. 点击保存，然后点击该模型的 **启用** 按钮

| 供应商 | 模型 ID | API 地址 | 获取 Key |
|--------|---------|----------|----------|
| DeepSeek | `deepseek-chat` 或 `deepseek-v4-pro` | `https://api.deepseek.com` | [platform.deepseek.com](https://platform.deepseek.com) |
| Kimi Code | `kimi-k2.6` | `https://api.kimi.com/coding/v1` | [www.kimi.com/code](https://www.kimi.com/code) |
| Moonshot | `moonshot-v1-128k` | `https://api.moonshot.cn/v1` | [platform.moonshot.cn](https://platform.moonshot.cn) |

---

## 修改 Codex 配置

编辑 `C:\Users\你的用户名\.codex\config.toml`，添加以下内容：

```toml
model_provider = "custom"
model = "你填的模型ID"

[model_providers]
[model_providers.custom]
name = "custom"
wire_api = "responses"
requires_openai_auth = true
base_url = "http://127.0.0.1:15800/v1"
```

> `model` 的值必须和前端"模型 ID"字段**完全一致**（也就是上表中的模型 ID），否则代理不会匹配到该模型。

保存后**重新打开 Codex**。

---

## 验证

打开 Codex，发一条消息。如果前端"日志"标签页看到请求记录，说明配置成功。

---

## 切换模型

在前端界面点击不同模型的"启用"按钮即可。会自动切换协议格式（Kimi Code 走 Anthropic，其他走 OpenAI）。

---

## 常见问题

**前端操作没反应（保存/启停按钮无效）**
→ Python 未安装或依赖未装好。运行 `pip install flask flask-cors` 后重启前端。

**Codex 提示连接错误或 502**
→ 确认代理已启动（前端界面显示"运行中"）。

**Kimi Code 报 400 错误**
→ 一般是推理模式导致。在前端把该模型的"推理"开关关掉。

**子代理创建失败**
→ Codex 线程上限，跟代理无关。稍后重试即可。

---

## 源码启动（开发者）

```bash
pip install -r requirements.txt
python proxy_manager.py
```

前端：

```bash
cd frontend
npm install
npm run electron:dev
```
