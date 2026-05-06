"""HTTP request handler — routes and helpers."""

import json
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.client import RemoteDisconnected

from .config import load_config, load_api_key, LOG_QUEUE
from .translate_openai import OpenAITranslateMixin
from .translate_anthropic import AnthropicTranslateMixin


class ProxyHandler(OpenAITranslateMixin, AnthropicTranslateMixin,
                   BaseHTTPRequestHandler):
    """Translates OpenAI Responses API to upstream provider APIs."""

    ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
    ROLE_MAP = {"developer": "system"}
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    def log_request(self, code="-", size="-"):
        msg = f"{self.command} {self.path} → {code}"
        LOG_QUEUE.put(msg)

    # ── HTTP routing ──────────────────────────────────────────────

    def do_GET(self):
        if self.path == "/v1/models":
            cfg = load_config()
            models = []
            for m in cfg.get("models", []):
                if m.get("enabled", True):
                    models.append({
                        "id": m["id"], "object": "model",
                        "created": 1700000000, "owned_by": "custom"
                    })
            self._json(200, {"object": "list", "data": models})
        elif self.path == "/v1/me":
            self._json(200, {
                "id": "user-proxy", "object": "user",
                "name": "Proxy User", "email": "proxy@local",
                "role": "owner", "added": 1700000000,
            })
        elif self.path == "/v1/organizations":
            self._json(200, {
                "object": "list", "data": [{
                    "id": "org-proxy", "object": "organization",
                    "name": "Proxy Org", "role": "owner",
                    "is_default": True,
                }]
            })
        elif self.path in ("/", "/health"):
            self._json(200, {"status": "ok"})
        elif self.path.startswith("/v1/"):
            self._json(200, {"object": "empty", "data": []})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/responses":
            self._handle_responses()
        elif self.path.startswith("/v1/"):
            self._pass_through(self.path[3:])
        else:
            self.send_response(404)
            self.end_headers()

    # ── routing helpers ───────────────────────────────────────────

    def _is_anthropic_upstream(self):
        cfg = load_config()
        base = cfg.get("deepseek_base", "")
        return "kimi.com/coding" in base

    def _handle_responses(self):
        body = self._read_body()
        stream = body.get("stream", False)

        if self._is_anthropic_upstream():
            req_body = self._to_anthropic(body)
            endpoint = "/messages"
        else:
            req_body = self._to_chat(body)
            endpoint = "/chat/completions"

        try:
            if stream:
                if self._is_anthropic_upstream():
                    self._stream_anthropic(req_body)
                else:
                    self._stream(req_body)
            else:
                data = self._fetch(endpoint, req_body)
                if self._is_anthropic_upstream():
                    self._json(200, self._from_anthropic_resp(data))
                else:
                    self._json(200, self._to_resp(data, req_body))
        except HTTPError as e:
            err = ""
            try:
                err = e.read().decode(errors="replace")[:300]
            except Exception:
                pass
            LOG_QUEUE.put(f"Upstream {e.code}: {err}")
            self._safe_json(e.code, {"error": f"Upstream {e.code}: {err}"})
        except ConnectionAbortedError:
            pass
        except Exception as e:
            LOG_QUEUE.put(f"FATAL: {e}")
            print(f"[FATAL] {traceback.format_exc()}",
                  file=sys.stderr, flush=True)
            self._safe_json(502, {"error": str(e)})

    def _pass_through(self, path):
        body = self._read_body()
        try:
            data = self._fetch(f"/{path}", body)
            self._json(200, data)
        except Exception as e:
            self._json(500, {"error": str(e)})

    # ── shared helpers ────────────────────────────────────────────

    @staticmethod
    def _extract_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict):
                    t = p.get("type", "")
                    if t in ("input_text", "output_text"):
                        parts.append(p.get("text", ""))
                    elif t == "input_image":
                        img_url = p.get("image_url", "")
                        if img_url:
                            parts.append("[image: " + str(img_url)[:80] + "]")
                    else:
                        parts.append(p.get("text", json.dumps(p)))
            return "\n".join(parts) if parts else ""
        return str(content) if content else ""

    @staticmethod
    def _extract_content_blocks(content):
        """Extract content as list of blocks, preserving image data."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        if isinstance(content, list):
            blocks = []
            for p in content:
                if isinstance(p, str):
                    blocks.append({"type": "text", "text": p})
                elif isinstance(p, dict):
                    t = p.get("type", "")
                    if t in ("input_text", "output_text"):
                        blocks.append({"type": "text", "text": p.get("text", "")})
                    elif t == "input_image":
                        img_url = p.get("image_url", "")
                        blocks.append({"type": "image", "image_url": img_url})
                    else:
                        blocks.append({"type": "text", "text": p.get("text", json.dumps(p))})
            return blocks if blocks else [{"type": "text", "text": ""}]
        return [{"type": "text", "text": str(content) if content else ""}]

    def _map_model(self, model_name):
        cfg = load_config()
        known = {m["id"] for m in cfg.get("models", [])
                 if m.get("enabled", True)}
        if model_name in known:
            return model_name
        for m in cfg.get("models", []):
            if m.get("enabled", True):
                LOG_QUEUE.put(f"Mapped model '{model_name}' → '{m['id']}'")
                return m["id"]
        return "deepseek-chat"

    def _read_body(self):
        cl = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(cl)) if cl > 0 else {}

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _safe_json(self, status, data):
        try:
            self._json(status, data)
        except Exception:
            pass

    def _sse(self, event_type, data):
        self.wfile.write(f"event: {event_type}\n".encode())
        self.wfile.write(
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def _gid(self, prefix=""):
        import uuid
        return f"{prefix}{uuid.uuid4().hex[:24]}"

    @classmethod
    def _do_fetch(cls, path, data, timeout=120):
        cfg = load_config()
        base = cfg.get("deepseek_base", "https://api.deepseek.com")
        key = load_api_key()
        is_anthropic = "kimi.com/coding" in base

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClaudeCode/1.0",
        }
        if is_anthropic:
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {key}"

        last_err = None
        for attempt in range(cls.MAX_RETRIES):
            try:
                req = Request(f"{base}{path}",
                              data=json.dumps(data).encode(),
                              headers=headers, method="POST")
                return urlopen(req, timeout=timeout)
            except (RemoteDisconnected, ConnectionResetError,
                    TimeoutError, OSError) as e:
                last_err = e
                if attempt < cls.MAX_RETRIES - 1:
                    time.sleep(cls.RETRY_DELAY * (attempt + 1))
        raise last_err or RuntimeError("max retries exceeded")

    def _fetch(self, path, data):
        resp = self._do_fetch(path, data)
        return json.loads(resp.read())
