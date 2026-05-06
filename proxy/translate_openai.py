"""OpenAI Responses API → Chat Completions API translation mixin."""

import json
import hashlib

from .config import _REASONING_CACHE, cache_reasoning


class OpenAITranslateMixin:
    """Methods for OpenAI Chat Completions format translation."""

    def _to_chat(self, req):
        messages = []
        instr = req.get("instructions", "")
        if instr:
            messages.append({"role": "system", "content": instr})

        for item in req.get("input", []):
            item_type = item.get("type", "")
            role = item.get("role", "")

            if item_type == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": self._extract_text(item.get("output", "")),
                })
                continue

            if item_type == "function_call":
                tc = {
                    "type": "function",
                    "id": item.get("call_id", ""),
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", ""),
                    }
                }
                if (messages and messages[-1].get("role") == "assistant"
                        and messages[-1].get("tool_calls")):
                    messages[-1]["tool_calls"].append(tc)
                else:
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc],
                    })
                continue

            if item_type in ("reasoning", "item_reference"):
                continue

            role = self.ROLE_MAP.get(role, role)
            if role not in self.ALLOWED_ROLES:
                role = "user"
            content = self._extract_text(item.get("content", ""))

            msg = {"role": role, "content": content}

            if role == "tool":
                tc_id = item.get("tool_call_id") or item.get("call_id", "")
                if tc_id:
                    msg["tool_call_id"] = tc_id

            tcs = item.get("tool_calls") or []
            if tcs and role == "assistant":
                chat_tcs = []
                for tc in tcs:
                    ctc = {"type": "function",
                           "id": tc.get("call_id", tc.get("id", ""))}
                    ctc["function"] = {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", ""),
                    }
                    chat_tcs.append(ctc)
                msg["tool_calls"] = chat_tcs

            messages.append(msg)

        # Re-inject cached reasoning_content
        for i, m in enumerate(messages):
            if (m.get("role") == "assistant"
                    and not m.get("reasoning_content") and i > 0):
                prev = messages[i - 1]
                pc = prev.get("content") or ""
                if isinstance(pc, list):
                    pc = json.dumps(pc, ensure_ascii=False)
                if pc:
                    key = hashlib.sha256(pc.encode()).hexdigest()[:16]
                    rc = _REASONING_CACHE.get(key)
                    if rc:
                        m["reasoning_content"] = rc

        model = self._map_model(req.get("model", "deepseek-v4-pro"))
        chat = {
            "model": model,
            "messages": messages,
            "stream": req.get("stream", False),
        }
        if "pro" in model or "reasoner" in model:
            chat["thinking"] = {"type": "enabled"}
        for k in ("temperature", "top_p", "frequency_penalty",
                  "presence_penalty"):
            if k in req:
                chat[k] = req[k]
        if "max_output_tokens" in req:
            chat["max_tokens"] = req["max_output_tokens"]
        if "tools" in req:
            tools = self._xlat_tools(req["tools"])
            if tools:
                chat["tools"] = tools
        if "tool_choice" in req:
            chat["tool_choice"] = req["tool_choice"]
        text_cfg = req.get("text", {})
        if isinstance(text_cfg, dict) and "format" in text_cfg:
            chat["response_format"] = text_cfg["format"]
        return chat

    def _xlat_tools(self, tools):
        import uuid
        result = []
        for tool in tools:
            t = tool.get("type", "")
            if t not in ("", "function", "custom", "namespace"):
                continue
            if "function" in tool:
                result.append(tool)
            elif "name" in tool:
                fn = {}
                for k in ("name", "description", "parameters", "strict"):
                    if k in tool:
                        fn[k] = tool[k]
                result.append({"type": "function", "function": fn})
            else:
                fn = {"name": tool.get(
                    "id", tool.get("name", f"tool_{uuid.uuid4().hex[:8]}"))}
                if "description" in tool:
                    fn["description"] = tool["description"]
                result.append({"type": "function", "function": fn})
        return result

    def _to_resp(self, chat_resp, chat_req=None):
        import time
        choice = (chat_resp.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        usage = chat_resp.get("usage", {})
        rid = chat_resp.get("id", self._gid("resp_"))
        mid = self._gid("msg_")
        content = msg.get("content") or ""
        parts = [{"type": "output_text", "text": content, "annotations": []}]
        output = [{"id": mid, "type": "message", "role": "assistant",
                   "content": parts}]

        rc = msg.get("reasoning_content", "")
        if rc and chat_req:
            cache_reasoning(chat_req, rc)

        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            output.append({
                "id": self._gid("fc_"),
                "type": "function_call",
                "call_id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", ""),
            })

        return {
            "id": rid, "object": "response",
            "created_at": chat_resp.get("created", int(time.time())),
            "model": chat_resp.get("model", "unknown"),
            "status": "completed", "output": output,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        }

    def _stream(self, chat_req):
        """SSE stream proxy for OpenAI Chat Completions format."""
        import json as json_mod
        resp = self._do_fetch("/chat/completions", chat_req)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        rid = self._gid("resp_")
        text_msg_id = self._gid("msg_")
        started = False
        text_closed = False
        full_text = ""
        full_reasoning = ""
        usage_info = {}
        tcs = {}
        output_items = []

        def open_text_msg():
            nonlocal text_closed
            if text_closed:
                new_id = self._gid("msg_")
                tcs["__text_msg_id"] = new_id
                self._sse("response.output_item.added", {
                    "type": "response.output_item.added",
                    "item": {"id": new_id, "type": "message",
                             "role": "assistant", "content": []}
                })
                self._sse("response.content_part.added", {
                    "type": "response.content_part.added",
                    "item_id": new_id,
                    "part": {"type": "output_text", "text": "",
                             "annotations": []},
                })
                return new_id
            return text_msg_id

        def close_text_msg():
            nonlocal text_closed, full_text
            if not text_closed and (full_text or started):
                text_closed = True
                cur_mid = tcs.pop("__text_msg_id", text_msg_id)
                self._sse("response.output_text.done", {
                    "type": "response.output_text.done",
                    "item_id": cur_mid, "output_index": 0,
                    "content_index": 0, "text": full_text,
                })
                self._sse("response.output_item.done", {
                    "type": "response.output_item.done",
                    "item": {"id": cur_mid, "type": "message",
                             "role": "assistant",
                             "content": [{"type": "output_text",
                                         "text": full_text,
                                         "annotations": []}]}
                })
                output_items.append({
                    "id": cur_mid, "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": full_text,
                                "annotations": []}]
                })

        for line in resp:
            raw = line.decode("utf-8").strip()
            if not raw or raw.startswith(":"):
                continue

            if raw == "data: [DONE]":
                if not text_closed and full_text:
                    close_text_msg()
                for idx in sorted(tcs.keys()):
                    if idx == "__text_msg_id":
                        continue
                    tc = tcs[idx]
                    self._sse("response.function_call_arguments.done", {
                        "type": "response.function_call_arguments.done",
                        "item_id": tc["fc_id"],
                        "name": tc["name"],
                        "arguments": tc["args"],
                    })
                    self._sse("response.output_item.done", {
                        "type": "response.output_item.done",
                        "item": {"id": tc["fc_id"],
                                 "type": "function_call",
                                 "call_id": tc["call_id"],
                                 "name": tc["name"],
                                 "arguments": tc["args"]}
                    })
                    output_items.append({
                        "id": tc["fc_id"], "type": "function_call",
                        "call_id": tc["call_id"], "name": tc["name"],
                        "arguments": tc["args"]
                    })
                if full_reasoning:
                    cache_reasoning(chat_req, full_reasoning)
                self._sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": rid, "object": "response",
                        "model": chat_req["model"],
                        "status": "completed", "output": output_items,
                        "usage": usage_info,
                    }
                })
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                continue

            if not raw.startswith("data:"):
                continue
            if raw == "data: [DONE]":
                continue

            chunk = json_mod.loads(raw[6:])
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta", {})

            if not started:
                started = True
                self._sse("response.created", {
                    "type": "response.created",
                    "response": {"id": rid, "object": "response",
                                 "model": chat_req["model"],
                                 "status": "in_progress", "output": []}
                })
                self._sse("response.output_item.added", {
                    "type": "response.output_item.added",
                    "item": {"id": text_msg_id, "type": "message",
                             "role": "assistant", "content": []}
                })
                self._sse("response.content_part.added", {
                    "type": "response.content_part.added",
                    "item_id": text_msg_id,
                    "part": {"type": "output_text", "text": "",
                             "annotations": []},
                })

            text = delta.get("content", "")
            if text:
                full_text += text
                self._sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": text_msg_id, "output_index": 0,
                    "content_index": 0, "delta": text,
                })

            rc_delta = delta.get("reasoning_content", "")
            if rc_delta:
                full_reasoning += rc_delta

            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)
                if idx not in tcs:
                    if not text_closed:
                        close_text_msg()
                    fc_id = self._gid("fc_")
                    tcs[idx] = {
                        "call_id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "fc_id": fc_id,
                        "args": "",
                    }
                    self._sse("response.output_item.added", {
                        "type": "response.output_item.added",
                        "item": {"id": fc_id, "type": "function_call",
                                 "call_id": tcs[idx]["call_id"],
                                 "name": tcs[idx]["name"],
                                 "arguments": ""}
                    })
                fn_name = tc.get("function", {}).get("name", "")
                if fn_name and not tcs[idx]["name"]:
                    tcs[idx]["name"] = fn_name
                fn_args = tc.get("function", {}).get("arguments", "")
                if fn_args:
                    tcs[idx]["args"] += fn_args
                    self._sse("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": tcs[idx]["fc_id"],
                        "delta": fn_args,
                    })

            u = chunk.get("usage")
            if u:
                usage_info = {
                    "input_tokens": u.get("prompt_tokens", 0),
                    "output_tokens": u.get("completion_tokens", 0),
                    "total_tokens": u.get("total_tokens", 0),
                }
