"""HTTP request handler - routes and helpers."""

import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.client import RemoteDisconnected

from .config import load_config, get_active_model_config, LOG_QUEUE
from .translate_openai import OpenAITranslateMixin
from .translate_anthropic import AnthropicTranslateMixin

MAX_BODY_SIZE = 10 * 1024 * 1024
MAX_RESPONSE_SIZE = 50 * 1024 * 1024

CORS_HEADERS = [
    ("Access-Control-Allow-Origin", "http://127.0.0.1:15801"),
    ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
    ("Access-Control-Allow-Headers", "Content-Type, Authorization"),
]


class ProxyHandler(OpenAITranslateMixin, AnthropicTranslateMixin,
                   BaseHTTPRequestHandler):
    """Translates OpenAI Responses API to upstream provider APIs."""

    ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
    ROLE_MAP = {"developer": "system"}
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    def _log_detail(self, msg):
        LOG_QUEUE.put_nowait(msg)

    def log_request(self, code="-", size="-"):
        cmd = "".join(c for c in self.command if c.isalpha())[:10]
        path = self.path[:200].replace("\n", "").replace("\r", "")
        msg = "{0} {1} -> {2}".format(cmd, path, str(code)[:10])
        LOG_QUEUE.put_nowait(msg)

    def do_OPTIONS(self):
        self.send_response(204)
        for name, value in CORS_HEADERS:
            self.send_header(name, value)
        self.end_headers()

    def do_GET(self):
        if self.path == "/v1/models":
            cfg = load_config()
            models = []
            for m in cfg.get("models", []):
                if m.get("enabled", False):
                    models.append({
                        "id": m["id"], "object": "model",
                        "created": 1700000000, "owned_by": "openai"
                    })
            self._json(200, {"object": "list", "data": models})
        elif self.path == "/v1/me":
            self._json(200, {
                "id": "user-proxy", "object": "user",
                "name": "Proxy User", "email": "proxy@local",
                "role": "owner", "added": 1700000000,
                "has_payg": True,
                "orgs": {"object": "list", "data": [{
                    "id": "org-proxy", "object": "organization",
                    "name": "Proxy Org", "role": "owner",
                    "is_default": True,
                    "has_payg": True,
                    "title": "personal",
                }]}
            })
        elif self.path == "/v1/organizations":
            self._json(200, {
                "object": "list", "data": [{
                    "id": "org-proxy", "object": "organization",
                    "name": "Proxy Org", "role": "owner",
                    "is_default": True,
                    "has_payg": True,
                    "title": "personal",
                    "personal": True,
                    "groups": [],
                }]
            })
        elif self.path in ("/v1/billing/subscription", "/v1/dashboard/billing/subscription"):
            self._json(200, {
                "object": "billing_subscription",
                "has_payment_method": True,
                "soft_limit": 500000,
                "hard_limit": 1000000,
                "account_name": "Proxy Org",
                "access_until": 2000000000,
            })
        elif self.path in ("/v1/usage", "/v1/dashboard/usage"):
            self._json(200, {
                "object": "usage",
                "total_usage": 0,
                "has_payg": True,
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
            # Pass unknown v1 endpoints through to upstream
            self._passthrough_post(self.path)
        else:
            self.send_response(404)
            self.end_headers()

    def _passthrough_post(self, path):
        """Forward an unknown POST request to the upstream API."""
        try:
            body = self._read_body()
            model_cfg = get_active_model_config()
            if not model_cfg:
                self._safe_json(500, {"error": "No model configured"})
                return
            base_url = model_cfg.get("base_url", "")
            api_key = model_cfg.get("api_key", "")
            if not api_key:
                self._safe_json(401, {"error": "API Key not configured"})
                return
            is_anthropic = self._is_anthropic_upstream(base_url, model_cfg)
            data = self._fetch_with_method(path.lstrip("/"), body, base_url, api_key, is_anthropic, method="POST")
            self._json(200, data)
        except HTTPError as e:
            err = ""
            try:
                err = e.read().decode(errors="replace")[:500]
            except Exception:
                pass
            self._safe_json(e.code, {"error": f"Upstream {e.code}: {err}"})
        except Exception as e:
            self._safe_json(502, {"error": str(e)})

    def _is_anthropic_upstream(self, base_url, model_cfg=None):
        if model_cfg:
            fmt = model_cfg.get("upstream_format", "openai")
            return fmt == "anthropic"
        return False

    def _handle_responses(self):
        try:
            body = self._read_body()
            stream = body.get("stream", False)
            model_cfg = get_active_model_config()

            if not model_cfg:
                self._safe_json(500, {"error": "No model configured"})
                return

            base_url = model_cfg.get("base_url", "https://api.deepseek.com")
            api_key = model_cfg.get("api_key", "")
            if not api_key:
                self._safe_json(401, {"error": "API Key not configured for this model. Please add it in the proxy settings."})
                return

            LOG_QUEUE.put_nowait(f"REQ model={model_cfg.get('id','?')} stream={stream} base={base_url[:50]}")

            is_anthropic = self._is_anthropic_upstream(base_url, model_cfg)

            if is_anthropic:
                req_body = self._to_anthropic(body)
                endpoint = "/messages"
            else:
                req_body = self._to_chat(body)
                endpoint = "/chat/completions"

            if stream:
                if is_anthropic:
                    self._stream_anthropic(req_body, base_url, api_key, is_anthropic)
                else:
                    self._stream(req_body, base_url, api_key, is_anthropic)
            else:
                data = self._fetch(endpoint, req_body, base_url, api_key, is_anthropic)
                if is_anthropic:
                    self._json(200, self._from_anthropic_resp(data))
                else:
                    self._json(200, self._to_resp(data, req_body))
        except ValueError as e:
            msg = str(e)
            if "too large" in msg:
                self._safe_json(413, {"error": msg})
            else:
                self._safe_json(400, {"error": msg})
        except HTTPError as e:
            err = ""
            try:
                err = e.read().decode(errors="replace")[:500]
            except Exception:
                pass
            LOG_QUEUE.put_nowait(f"Upstream {e.code}: {err}")
            self._safe_json(e.code, {"error": f"Upstream {e.code}: {err}"})
        except ConnectionAbortedError:
            pass
        except Exception as e:
            LOG_QUEUE.put_nowait(f"FATAL: {e}")
            traceback.print_exc()
            self._safe_json(502, {"error": str(e)})

    def _pass_through(self, path):
        body = self._read_body()
        try:
            model_cfg = get_active_model_config()
            base_url = model_cfg.get("base_url", "") if model_cfg else ""
            api_key = model_cfg.get("api_key", "") if model_cfg else ""
            data = self._fetch_with_method("/{0}".format(path), body, base_url, api_key, method=self.command)
            self._json(200, data)
        except Exception as e:
            self._json(500, {"error": str(e)})

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
        if content is None:
            return ""
        return str(content) if content else ""

    @staticmethod
    def _extract_content_blocks(content):
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
        models = cfg.get("models", [])
        enabled_models = [m for m in models if m.get("enabled", True)]
        if not enabled_models:
            LOG_QUEUE.put_nowait("No enabled models, falling back to deepseek-chat")
            return "deepseek-chat"
        known = {m["id"] for m in enabled_models}
        if model_name in known:
            return model_name
        for m in models:
            if m["id"] == model_name:
                LOG_QUEUE.put_nowait("Model '{0}' disabled, using fallback".format(model_name))
                break
        fallback = enabled_models[0]["id"]
        LOG_QUEUE.put_nowait("Mapped unknown model '{0}' -> '{1}'".format(model_name, fallback))
        return fallback

    def _read_body(self):
        try:
            cl = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            raise ValueError("Invalid Content-Length header")
        if cl > MAX_BODY_SIZE:
            raise ValueError("Request body too large: {0} bytes".format(cl))
        if cl <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(cl))
        except json.JSONDecodeError as e:
            LOG_QUEUE.put_nowait(f"JSON parse error: {e}")
            raise ValueError("Invalid JSON in request body")

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in CORS_HEADERS:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _safe_json(self, status, data):
        try:
            self._json(status, data)
        except Exception:
            pass

    def _sse(self, event_type, data):
        try:
            self.wfile.write("event: {0}\n".format(event_type).encode())
            self.wfile.write(
                "data: {0}\n\n".format(json.dumps(data, ensure_ascii=False)).encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _gid(self, prefix=""):
        import uuid
        return "{0}{1}".format(prefix, uuid.uuid4().hex[:24])

    @classmethod
    def _do_fetch(cls, path, data, base_url, api_key, is_anthropic=False, timeout=120):
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClaudeCode/1.0",
        }
        if is_anthropic:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = "Bearer {0}".format(api_key)

        last_err = None
        for attempt in range(cls.MAX_RETRIES):
            try:
                req = Request("{0}{1}".format(base_url, path),
                              data=json.dumps(data).encode(),
                              headers=headers, method="POST")
                return urlopen(req, timeout=timeout)
            except HTTPError as e:
                if 400 <= e.code < 500:
                    raise
                last_err = e
                try:
                    e.close()
                except Exception:
                    pass
                if attempt < cls.MAX_RETRIES - 1:
                    time.sleep(cls.RETRY_DELAY * (2 ** attempt))
            except (RemoteDisconnected, ConnectionResetError,
                    TimeoutError, OSError) as e:
                last_err = e
                if attempt < cls.MAX_RETRIES - 1:
                    time.sleep(cls.RETRY_DELAY * (2 ** attempt))
        raise last_err or RuntimeError("max retries exceeded")

    def _fetch(self, path, data, base_url, api_key, is_anthropic=False):
        resp = self._do_fetch(path, data, base_url, api_key, is_anthropic)
        try:
            raw = resp.read(MAX_RESPONSE_SIZE + 1)
            if len(raw) > MAX_RESPONSE_SIZE:
                raise ValueError("Upstream response too large: {0}+ bytes".format(MAX_RESPONSE_SIZE))
            return json.loads(raw)
        finally:
            resp.close()

    def _fetch_with_method(self, path, data, base_url, api_key, is_anthropic=False, method="POST"):
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ClaudeCode/1.0",
        }
        for hdr in ("X-Request-ID", "X-Client-Name"):
            val = self.headers.get(hdr)
            if val:
                headers[hdr] = val

        if is_anthropic:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = "Bearer {0}".format(api_key)

        req_data = json.dumps(data).encode() if data else b""
        req = Request("{0}{1}".format(base_url, path),
                      data=req_data,
                      headers=headers, method=method)
        resp = urlopen(req, timeout=120)
        try:
            return json.loads(resp.read())
        finally:
            resp.close()


