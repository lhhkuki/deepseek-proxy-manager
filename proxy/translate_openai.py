"""OpenAI Responses API to Chat Completions API translation mixin."""

import json
import hashlib

from .config import _REASONING_CACHE, _REASONING_LOCK, cache_reasoning, LOG_QUEUE


class OpenAITranslateMixin:
    """Methods for OpenAI Chat Completions format translation."""

    def _to_chat(self, req):
        messages = []
        instr = req.get("instructions", "")
        has_system_from_input = False

        for item in req.get("input", []):
            item_type = item.get("type", "")
            role = item.get("role", "")

            if item_type == "function_call_output":
                output_content = item.get("output", "")
                blocks = self._extract_content_blocks(output_content)
                has_image = any(b.get("type") == "image" for b in blocks)
                if has_image:
                    content_parts = []
                    for b in blocks:
                        if b.get("type") == "image":
                            content_parts.append({"type": "image_url", "image_url": {"url": b.get("image_url", "")}})
                        else:
                            content_parts.append({"type": "text", "text": b.get("text", "")})
                    messages.append({"role": "tool", "tool_call_id": item.get("call_id", ""), "content": content_parts})
                else:
                    messages.append({"role": "tool", "tool_call_id": item.get("call_id", ""), "content": self._extract_text(output_content)})
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
            if role == "system":
                has_system_from_input = True
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

        if instr and not has_system_from_input:
            messages.insert(0, {"role": "system", "content": instr})

        # Inject cached reasoning_content where available
        for i, m in enumerate(messages):
            if (m.get("role") == "assistant"
                    and not m.get("reasoning_content") and i > 0):
                prev = messages[i - 1]
                pc = prev.get("content") or ""
                if isinstance(pc, list):
                    pc = json.dumps(pc, ensure_ascii=False)
                if pc:
                    key = hashlib.sha256(pc.encode()).hexdigest()
                    with _REASONING_LOCK:
                        rc = _REASONING_CACHE.get(key)
                    if rc:
                        m["reasoning_content"] = rc
        model = self._map_model(req.get("model", "deepseek-v4-pro"))
        chat = {
            "model": model,
            "messages": messages,
            "stream": req.get("stream", False),
        }
        if req.get("stream"):
            chat["stream_options"] = {"include_usage": True}
        # Ensure tool_calls messages have reasoning_content before enabling thinking
        reasoning = req.get("reasoning")
        if reasoning is None:
            from .config import get_active_model_config
            mc = get_active_model_config()
            reasoning = mc.get("reasoning", False) if mc else False
        if reasoning:
            fixed = 0
            for i, m in enumerate(messages):
                if (m.get("role") == "assistant" and m.get("tool_calls")
                        and not m.get("reasoning_content")):
                    m["reasoning_content"] = ""
                    fixed += 1
            LOG_QUEUE.put(f"Thinking enabled, fixed {fixed} missing reasoning_content")
            chat["thinking"] = {"type": "enabled", "budget_tokens": 8192}
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
            chat["tool_choice"] = self._xlat_tool_choice(req["tool_choice"])
        text_cfg = req.get("text", {})
        if isinstance(text_cfg, dict) and "format" in text_cfg:
            chat["response_format"] = text_cfg["format"]
        return chat

    def _xlat_tools(self, tools):
        import uuid
        result = []
        for tool in tools:
            t = tool.get("type", "")
            if t == "web_search":
                result.append({
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web for current information",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"]
                        }
                    }
                })
                continue
            # Pass through all tool types — let the model decide what it can use
            if "function" in tool:
                result.append(tool)
            elif "name" in tool:
                fn = {}
                for k in ("name", "description", "parameters", "strict"):
                    if k in tool:
                        fn[k] = tool[k]
                result.append({"type": "function", "function": fn})
            else:
                result.append(tool)
        return result

    def _xlat_tool_choice(self, tool_choice):
        if isinstance(tool_choice, str):
            if tool_choice in ("auto", "none", "required"):
                return tool_choice
            if tool_choice == "any":
                return "required"
            return tool_choice
        if isinstance(tool_choice, dict):
            tc_type = tool_choice.get("type", "")
            if tc_type in ("function", "tool"):
                return {"type": "function",
                        "function": {"name": tool_choice.get("name", "")}}
        return tool_choice

    def _to_resp(self, chat_resp, chat_req):
        import json as json_mod
        rid = chat_resp.get("id", "")
        model = chat_resp.get("model", chat_req.get("model", ""))
        choice = (chat_resp.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        tcs = msg.get("tool_calls") or []

        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            cache_reasoning(chat_req, reasoning)

        output_items = []
        if content:
            output_items.append({
                "id": self._gid("msg_"),
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content,
                             "annotations": []}],
            })
        elif reasoning:
            # V4 Pro consumed all tokens on reasoning — include it as output
            output_items.append({
                "id": self._gid("msg_"),
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": reasoning[:500],
                             "annotations": []}],
            })
        for tc in tcs:
            tc_name = tc.get("function", {}).get("name", "")
            output_items.append({
                "id": tc.get("id", self._gid("fc_")),
                "type": "function_call",
                "call_id": tc.get("id", ""),
                "name": tc_name,
                "arguments": tc.get("function", {}).get("arguments", ""),
            })
            # Auto-execute web_search and include results inline
            if tc_name == "web_search":
                try:
                    args = tc.get("function", {}).get("arguments", "{}")
                    if isinstance(args, str):
                        args = json_mod.loads(args)
                    query = args.get("query", "")
                    from .web_search import search
                    search_result = search(query)
                    output_items.append({
                        "id": self._gid("fc_output_"),
                        "type": "function_call_output",
                        "call_id": tc.get("id", ""),
                        "output": search_result,
                    })
                except Exception:
                    pass

        usage = chat_resp.get("usage", {})
        return {
            "id": rid,
            "object": "response",
            "model": model,
            "status": "completed",
            "output": output_items,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    def _stream(self, chat_req, base_url, api_key, is_anthropic=False):
        import json as json_mod

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
        tcs = {}
        usage_info = {"input_tokens": 0, "output_tokens": 0,
                      "total_tokens": 0}
        output_items = []

        def close_text_msg():
            nonlocal text_closed
            text_closed = True
            self._sse("response.output_text.done", {
                "type": "response.output_text.done",
                "item_id": text_msg_id, "output_index": 0,
                "content_index": 0, "text": full_text,
            })
            self._sse("response.output_item.done", {
                "type": "response.output_item.done",
                "item": {"id": text_msg_id, "type": "message",
                         "role": "assistant",
                         "content": [{"type": "output_text",
                                      "text": full_text,
                                      "annotations": []}]}
            })

        try:
            resp = self._do_fetch("/chat/completions", chat_req, base_url, api_key, is_anthropic)
        except Exception:
            self._sse("response.completed", {
                "type": "response.completed",
                "response": {
                    "id": rid, "object": "response",
                    "model": chat_req["model"],
                    "status": "failed",
                    "output": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                }
            })
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
            return

        try:
            for raw in resp:
                if not raw:
                    continue
                raw = raw.decode(errors="replace")
                if raw.strip() == "data: [DONE]":
                    if not text_closed and full_text:
                        close_text_msg()
                    for tc in tcs.values():
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
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            if full_reasoning:
                cache_reasoning(chat_req, full_reasoning)
            # Ensure stream always gets completion
            if not started and not text_closed:
                # No data was read — return error as SSE
                self._sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": rid, "object": "response",
                        "model": chat_req["model"],
                        "status": "failed", "output": [],
                        "usage": usage_info,
                    }
                })
            elif started:
                if not text_closed and full_text:
                    close_text_msg()
                for tc in tcs.values():
                    if tc.get("fc_id"):
                        self._sse("response.function_call_arguments.done", {
                            "type": "response.function_call_arguments.done",
                            "item_id": tc["fc_id"],
                            "name": tc.get("name", ""),
                            "arguments": tc.get("args", ""),
                        })
                        self._sse("response.output_item.done", {
                            "type": "response.output_item.done",
                            "item": {"id": tc["fc_id"], "type": "function_call",
                                     "call_id": tc["call_id"],
                                     "name": tc.get("name", ""),
                                     "arguments": tc.get("args", "")}
                        })
                        output_items.append({
                            "id": tc["fc_id"], "type": "function_call",
                            "call_id": tc["call_id"],
                            "name": tc.get("name", ""),
                            "arguments": tc.get("args", "")
                        })
                self._sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": rid, "object": "response",
                        "model": chat_req["model"],
                        "status": "completed", "output": output_items,
                        "usage": usage_info,
                    }
                })
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
            total_out = usage_info.get("output_tokens", 0)
            text_len = len(full_text)
            try:
                resp.close()
            except Exception:
                pass
