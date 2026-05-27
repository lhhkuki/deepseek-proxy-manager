"""Launch Codex with CDP and inject small plugin-unlock patches."""

import base64
import glob
import hashlib
import json
import os
import socket
import struct
import subprocess
import shutil
import tempfile
import time
import urllib.error
import urllib.request

DEFAULT_CDP_PORT = 9231
LAUNCHER_USER_DATA_ENV = "CODEX_LAUNCHER_USER_DATA_DIR"
_codex_process = None
_last_inject = {
    "ok": False,
    "message": "尚未注入",
    "target": "",
    "updated_at": "",
}


INJECT_SCRIPT = r"""
(() => {
  const marker = "__aiProxyManagerCodexUnlockInstalled";
  if (window[marker]?.version === 1) return "already-installed";
  window[marker] = { version: 1, installedAt: Date.now() };

  const selectors = {
    pluginNavButton: 'nav[role="navigation"] button.h-token-nav-row.w-full',
    pluginSvgPath: 'svg path[d^="M7.94562 14.0277"]',
    disabledInstallButton: 'button:disabled, button[aria-disabled="true"], [role="button"][aria-disabled="true"], button[data-disabled], [role="button"][data-disabled], button.cursor-not-allowed, [role="button"].cursor-not-allowed, button.pointer-events-none, [role="button"].pointer-events-none',
  };

  function reactFiberFrom(element) {
    return Object.keys(element || {}).find((key) => key.startsWith("__reactFiber"));
  }

  function reactPropsKeyFrom(element) {
    return Object.keys(element || {}).find((key) => key.startsWith("__reactProps"));
  }

  function authContextValueFrom(element) {
    const fiberKey = reactFiberFrom(element);
    for (let fiber = fiberKey ? element[fiberKey] : null; fiber; fiber = fiber.return) {
      for (const value of [fiber.memoizedProps?.value, fiber.pendingProps?.value]) {
        if (value && typeof value === "object" && typeof value.setAuthMethod === "function" && "authMethod" in value) {
          return value;
        }
      }
    }
    return null;
  }

  function spoofChatGPTAuthMethod(element) {
    const auth = authContextValueFrom(element);
    if (!auth || auth.authMethod === "chatgpt") return false;
    auth.setAuthMethod("chatgpt");
    return true;
  }

  function pluginEntryButton() {
    const byIcon = document.querySelector(`${selectors.pluginNavButton} ${selectors.pluginSvgPath}`)?.closest("button");
    if (byIcon) return byIcon;
    return Array.from(document.querySelectorAll(selectors.pluginNavButton))
      .find((button) => /^(插件|Plugins)(\s+-\s+.*)?$/i.test((button.textContent || "").trim())) || null;
  }

  function labelPluginEntry(button) {
    const labelTextNode = Array.from(button.querySelectorAll("span, div")).reverse()
      .flatMap((node) => Array.from(node.childNodes))
      .find((node) => node.nodeType === 3 && /^(插件|Plugins)( - 已解锁| - Unlocked)?$/i.test((node.nodeValue || "").trim()));
    if (!labelTextNode) return;
    const current = (labelTextNode.nodeValue || "").trim();
    labelTextNode.nodeValue = /^Plugins/i.test(current) ? "Plugins - Unlocked" : "插件 - 已解锁";
  }

  function enablePluginEntry() {
    const button = pluginEntryButton();
    if (!button) return;
    spoofChatGPTAuthMethod(button);
    button.disabled = false;
    button.removeAttribute("disabled");
    button.style.display = "";
    button.querySelectorAll("*").forEach((node) => { node.style.display = ""; });
    const propsKey = reactPropsKeyFrom(button);
    if (propsKey) button[propsKey].disabled = false;
    labelPluginEntry(button);
    if (button.dataset.aiProxyManagerPluginEnabled === "true") return;
    button.dataset.aiProxyManagerPluginEnabled = "true";
    button.addEventListener("click", () => spoofChatGPTAuthMethod(button), true);
  }

  function installCandidates() {
    const nodes = Array.from(document.querySelectorAll(selectors.disabledInstallButton));
    return Array.from(new Set(nodes.map((node) => node.closest?.("button, [role='button']") || node)));
  }

  function patchReactDisabledProps(element) {
    const propsKey = reactPropsKeyFrom(element);
    if (!propsKey) return;
    const props = element[propsKey];
    if (!props || typeof props !== "object") return;
    props.disabled = false;
    props["aria-disabled"] = false;
    props["data-disabled"] = undefined;
  }

  function unlockElement(element) {
    if (!(element instanceof HTMLElement)) return;
    if ("disabled" in element) element.disabled = false;
    element.removeAttribute("disabled");
    element.removeAttribute("aria-disabled");
    element.removeAttribute("data-disabled");
    element.removeAttribute("inert");
    element.classList.remove("disabled", "opacity-50", "cursor-not-allowed", "pointer-events-none");
    element.style.pointerEvents = "auto";
    element.style.opacity = "";
    element.style.cursor = "pointer";
    element.tabIndex = 0;
    patchReactDisabledProps(element);
  }

  function unlockInstallButtons() {
    installCandidates().forEach((button) => {
      const text = (button.textContent || "").trim();
      if (!(/^安装\s*/.test(text) || /^Install\s*/i.test(text) || text === "强制安装")) return;
      [button, ...button.querySelectorAll?.("button, [role='button'], [disabled], [aria-disabled], [data-disabled], .cursor-not-allowed, .pointer-events-none") || []]
        .forEach(unlockElement);
      if (!button.dataset.aiProxyManagerForcedInstall) {
        button.dataset.aiProxyManagerForcedInstall = "true";
        ["pointerdown", "mousedown", "mouseup", "click", "focus"].forEach((eventName) => {
          button.addEventListener(eventName, () => unlockInstallButtons(), true);
        });
      }
    });
  }

  function scan() {
    enablePluginEntry();
    unlockInstallButtons();
  }

  scan();
  window[marker].timer = setInterval(scan, 1000);
  window[marker].observer = new MutationObserver(scan);
  window[marker].observer.observe(document.documentElement, { childList: true, subtree: true });
  return "installed";
})();
"""


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _local_app_data():
    return os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")


def launcher_user_data_dir():
    explicit = os.environ.get(LAUNCHER_USER_DATA_ENV, "").strip()
    path = explicit or os.path.join(_local_app_data(), "AI Proxy Manager", "CodexLauncherProfile")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), "AI Proxy Manager", "CodexLauncherProfile")
        os.makedirs(fallback, exist_ok=True)
        return fallback


def _launcher_cache_root():
    path = os.path.join(_local_app_data(), "AI Proxy Manager", "CodexAppCache")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        fallback = os.path.join(tempfile.gettempdir(), "AI Proxy Manager", "CodexAppCache")
        os.makedirs(fallback, exist_ok=True)
        return fallback


def find_codex_exe():
    explicit = os.environ.get("CODEX_APP_EXE", "").strip()
    if explicit and os.path.exists(explicit):
        return explicit
    candidates = []
    candidates.extend(_running_gui_codex_paths())
    candidates.extend(_powershell_windowsapps_codex_paths())
    for root in _windows_apps_roots():
        pattern = os.path.join(root, "OpenAI.Codex_*", "app", "Codex.exe")
        candidates.extend(path for path in glob.glob(pattern) if os.path.isfile(path))
    pattern = os.path.join(_local_app_data(), "OpenAI", "Codex", "bin", "*", "codex.exe")
    candidates.extend(path for path in glob.glob(pattern) if os.path.isfile(path))
    if not candidates:
        return ""
    candidates.sort(key=lambda path: (_codex_path_rank(path), os.path.getmtime(path)), reverse=True)
    return candidates[0]


def _running_gui_codex_paths():
    paths = []
    for proc in codex_processes():
        path = proc.get("path", "")
        normalized = path.lower().replace("/", "\\")
        if "\\windowsapps\\openai.codex_" in normalized and normalized.endswith("\\app\\codex.exe"):
            paths.append(path)
    return paths


def _powershell_windowsapps_codex_paths():
    script = (
        "$pkg = Get-AppxPackage OpenAI.Codex -ErrorAction SilentlyContinue | "
        "Sort-Object Version -Descending | Select-Object -First 1; "
        "if ($pkg) { "
        "$p1 = Join-Path $pkg.InstallLocation 'app\\Codex.exe'; "
        "$p2 = Join-Path $pkg.InstallLocation 'Codex.exe'; "
        "if (Test-Path $p1) { $p1 } elseif (Test-Path $p2) { $p2 } "
        "}; "
        "Get-ChildItem 'C:\\Program Files\\WindowsApps\\OpenAI.Codex_*\\app\\Codex.exe' "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName"
    )
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    paths = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if path and os.path.exists(path):
            paths.append(path)
    return list(dict.fromkeys(paths))


def _windows_apps_roots():
    roots = []
    for key in ("ProgramFiles", "ProgramW6432"):
        value = os.environ.get(key)
        if value:
            roots.append(os.path.join(value, "WindowsApps"))
    roots.append(r"C:\Program Files\WindowsApps")
    return list(dict.fromkeys(roots))


def _codex_path_rank(path):
    normalized = path.lower().replace("/", "\\")
    if "\\windowsapps\\openai.codex_" in normalized and normalized.endswith("\\app\\codex.exe"):
        return 4
    if os.path.basename(path).lower() == "codex.exe" and os.path.isfile(os.path.join(os.path.dirname(path), "resources", "app.asar")):
        return 3
    if "\\app\\resources\\codex.exe" in normalized:
        return 1
    return 1


def _is_windowsapps_gui_exe(path):
    normalized = path.lower().replace("/", "\\")
    return "\\windowsapps\\openai.codex_" in normalized and normalized.endswith("\\app\\codex.exe")


def _codex_app_source_dir(exe):
    if not exe:
        return ""
    if os.path.basename(exe).lower() != "codex.exe":
        return ""
    app_dir = os.path.dirname(exe)
    return app_dir if os.path.isfile(os.path.join(app_dir, "resources", "app.asar")) else ""


def _cached_codex_app_dir(source_app_dir):
    package_dir = os.path.basename(os.path.dirname(source_app_dir))
    cache_name = package_dir if package_dir.lower().startswith("openai.codex_") else hashlib.sha256(source_app_dir.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_launcher_cache_root(), cache_name, "app")


def _copy_codex_app_dir(source_app_dir, target_app_dir):
    os.makedirs(os.path.dirname(target_app_dir), exist_ok=True)
    if os.name == "nt":
        command = [
            "robocopy",
            source_app_dir,
            target_app_dir,
            "/MIR",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/NP",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if result.returncode <= 7:
            return
        raise RuntimeError((result.stderr or result.stdout or f"robocopy failed: {result.returncode}").strip())
    if os.path.isdir(target_app_dir):
        shutil.rmtree(target_app_dir)
    shutil.copytree(source_app_dir, target_app_dir)


def prepare_codex_launch_exe(source_exe):
    source_app_dir = _codex_app_source_dir(source_exe)
    if not source_app_dir:
        return source_exe
    if not _is_windowsapps_gui_exe(source_exe):
        return source_exe
    target_app_dir = _cached_codex_app_dir(source_app_dir)
    target_exe = os.path.join(target_app_dir, "Codex.exe")
    source_version = os.path.basename(os.path.dirname(source_app_dir))
    marker = os.path.join(target_app_dir, ".ai-proxy-source-version")
    if not os.path.isfile(target_exe) or not os.path.isfile(marker) or open(marker, "r", encoding="utf-8").read().strip() != source_version:
        _copy_codex_app_dir(source_app_dir, target_app_dir)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(source_version)
    return target_exe


def expected_codex_launch_exe(source_exe):
    source_app_dir = _codex_app_source_dir(source_exe)
    if source_app_dir and _is_windowsapps_gui_exe(source_exe):
        return os.path.join(_cached_codex_app_dir(source_app_dir), "Codex.exe")
    return source_exe


def _codex_process_rows():
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "Get-Process | "
            "Where-Object { "
            "($_.ProcessName -eq 'Codex') -or "
            "($_.ProcessName -eq 'codex' -and $_.Path -like '*OpenAI*Codex*') "
            "} | Select-Object Id,ProcessName,Path | ConvertTo-Json -Compress"
        ),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def codex_processes():
    rows = []
    for row in _codex_process_rows():
        try:
            pid = int(row.get("Id"))
        except (TypeError, ValueError):
            continue
        rows.append({
            "id": pid,
            "name": str(row.get("ProcessName") or ""),
            "path": str(row.get("Path") or ""),
        })
    return rows


def terminate_existing_codex(timeout=8):
    current_pid = os.getpid()
    killed = []
    for proc in codex_processes():
        pid = proc["id"]
        if pid == current_pid:
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F", "/T"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            killed.append(proc)
        except Exception:
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not codex_processes():
            break
        time.sleep(0.25)
    return killed


def stop_launched_codex(timeout=8):
    global _codex_process
    killed = []
    if _codex_process is None:
        return killed
    if _codex_process.poll() is not None:
        _codex_process = None
        return killed
    pid = _codex_process.pid
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        killed.append({"id": pid, "name": "Codex", "path": ""})
    except Exception:
        pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _codex_process.poll() is not None:
            break
        time.sleep(0.25)
    if _codex_process.poll() is not None:
        _codex_process = None
    return killed


def _http_json(path, port=DEFAULT_CDP_PORT, timeout=1.5):
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8", errors="replace"))


def cdp_available(port=DEFAULT_CDP_PORT):
    try:
        _http_json("/json/version", port=port)
        return True
    except Exception:
        return False


def launcher_status(port=DEFAULT_CDP_PORT):
    exe = find_codex_exe()
    launch_exe = ""
    launch_exe = expected_codex_launch_exe(exe) if exe else ""
    targets = []
    if cdp_available(port):
        try:
            targets = [
                {"title": item.get("title", ""), "url": item.get("url", ""), "type": item.get("type", "")}
                for item in _http_json("/json/list", port=port)
            ]
        except Exception:
            targets = []
    running = _codex_process is not None and _codex_process.poll() is None
    return {
        "codex_exe": exe,
        "launch_exe": launch_exe,
        "user_data_dir": launcher_user_data_dir(),
        "debug_port": port,
        "cdp_available": cdp_available(port),
        "launched_by_manager": running,
        "last_inject": dict(_last_inject),
        "processes": codex_processes(),
        "targets": targets,
    }


def launch_codex(port=DEFAULT_CDP_PORT, terminate_existing=False):
    global _codex_process
    if cdp_available(port):
        return launcher_status(port)
    if terminate_existing:
        terminate_existing_codex()
    exe = find_codex_exe()
    if not exe:
        raise FileNotFoundError("未找到 Codex 可执行文件，请设置 CODEX_APP_EXE")
    args = [
        exe,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={launcher_user_data_dir()}",
        "--no-first-run",
    ]
    _codex_process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.time() + 12
    while time.time() < deadline:
        if cdp_available(port):
            break
        if _codex_process.poll() is not None:
            raise RuntimeError("Codex 启动后立即退出，可能已有普通 Codex 进程占用单实例")
        time.sleep(0.35)
    if not cdp_available(port):
        raise TimeoutError("Codex 已启动，但 CDP 调试端口未就绪")
    return launcher_status(port)


def launch_codex(port=DEFAULT_CDP_PORT, terminate_existing=False):
    global _codex_process
    if cdp_available(port):
        return launcher_status(port)
    if terminate_existing:
        terminate_existing_codex()

    source_exe = find_codex_exe()
    if not source_exe:
        raise FileNotFoundError("Codex executable was not found. Set CODEX_APP_EXE if it is installed in a custom location.")

    launch_exe = prepare_codex_launch_exe(source_exe)
    user_data_dir = launcher_user_data_dir()
    args = [
        launch_exe,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
    ]
    env = os.environ.copy()
    env["CODEX_ELECTRON_USER_DATA_PATH"] = user_data_dir
    _codex_process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    deadline = time.time() + 12
    while time.time() < deadline:
        if cdp_available(port):
            break
        if _codex_process.poll() is not None:
            raise RuntimeError(f"Codex exited immediately. launch_exe={launch_exe}; user_data_dir={user_data_dir}")
        time.sleep(0.35)
    if not cdp_available(port):
        raise TimeoutError(f"Codex started, but CDP port {port} did not become available.")
    return launcher_status(port)


def _websocket_accept(key):
    raw = (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")


def _read_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("CDP WebSocket closed")
        data += chunk
    return data


def _send_ws_text(sock, payload):
    data = payload.encode("utf-8")
    header = bytearray([0x81])
    length = len(data)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    mask = os.urandom(4)
    header.extend(mask)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
    sock.sendall(bytes(header) + masked)


def _recv_ws_text(sock):
    first, second = _read_exact(sock, 2)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(sock, 8))[0]
    mask = _read_exact(sock, 4) if masked else b""
    payload = _read_exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    if opcode == 0x8:
        raise ConnectionError("CDP WebSocket closed")
    if opcode not in (0x1, 0x2):
        return ""
    return payload.decode("utf-8", errors="replace")


def _cdp_call(ws_url, method, params=None, timeout=5):
    if not ws_url.startswith("ws://"):
        raise ValueError("只支持本地 ws:// CDP 地址")
    rest = ws_url[len("ws://"):]
    host_port, path = rest.split("/", 1)
    host, port_text = host_port.rsplit(":", 1)
    sock = socket.create_connection((host, int(port_text)), timeout=timeout)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError("CDP WebSocket handshake failed")
        expected = _websocket_accept(key).encode("ascii")
        if expected not in response:
            raise ConnectionError("CDP WebSocket accept mismatch")

        message_id = 1
        _send_ws_text(sock, json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            text = _recv_ws_text(sock)
            if not text:
                continue
            data = json.loads(text)
            if data.get("id") == message_id:
                if "error" in data:
                    raise RuntimeError(data["error"])
                return data.get("result", {})
        raise TimeoutError("CDP call timed out")
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _page_targets(port):
    targets = _http_json("/json/list", port=port, timeout=2)
    return [
        item for item in targets
        if item.get("webSocketDebuggerUrl") and item.get("type") in ("page", "webview")
    ]


def inject_unlock_script(port=DEFAULT_CDP_PORT):
    global _last_inject
    if not cdp_available(port):
        raise RuntimeError("CDP 未连接，请先用启动器启动 Codex")
    targets = _page_targets(port)
    if not targets:
        raise RuntimeError("未找到可注入的 Codex 页面")
    target = targets[0]
    result = _cdp_call(
        target["webSocketDebuggerUrl"],
        "Runtime.evaluate",
        {
            "expression": INJECT_SCRIPT,
            "awaitPromise": False,
            "returnByValue": True,
        },
    )
    value = result.get("result", {}).get("value", "")
    _last_inject = {
        "ok": True,
        "message": f"注入完成：{value or 'ok'}",
        "target": target.get("title") or target.get("url") or "Codex",
        "updated_at": _now(),
    }
    return dict(_last_inject)


def launch_and_inject(port=DEFAULT_CDP_PORT, terminate_existing=False):
    status = launch_codex(port, terminate_existing=terminate_existing)
    inject = inject_unlock_script(port)
    status = launcher_status(port)
    status["last_inject"] = inject
    return status
