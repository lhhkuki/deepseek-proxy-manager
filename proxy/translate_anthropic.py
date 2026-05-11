"""OpenAI Responses API → Anthropic Messages API translation mixin."""

import json as json_mod
import hashlib
import uuid as _uuid

from .config import LOG_QUEUE


class AnthropicTranslateMixin:
    """Methods for Anthropic Messages format translation."""

    def _to_anthropic(self, req):
        messages = []
        system_parts = []

        instr = req.get("instructions", "")
        if instr:
            system_parts.append(instr)

        # Collect output call_ids to filter orphaned function_calls
        output_ids = set()
        for item in req.get("input", []):
            if item.get("type") == "function_call_output":
                cid = item.get("call_id", "")
                if cid:
                    output_ids.add(cid)

        for item in req.get("input", []):
            item_type = item.get("type", "")
            role = item.get("role", "")

            # ── function_call_output → user message with tool_result
            if item_type == "function_call_output":
                tc_id = item.get("call_id", "")
                output_content = item.get("output", "")
                blocks = self._extract_content_blocks(output_content)
                has_image = any(b.get("type") == "image" for b in blocks)
                if has_image:
                    content_blocks = []
                    for b in blocks:
                        if b.get("type") == "image":
                            img_url = b.get("image_url", "")
                            if img_url.startswith("data:"):
                                anthro_img = self._convert_image_to_anthropic(img_url)
                                if anthro_img:
                                    content_blocks.append(anthro_img)
                            else:
                                content_blocks.append({"type": "image", "source": {"type": "url", "url": img_url}})
                        else:
                            content_blocks.append({"type": "text", "text": b.get("text", "")})
                    block = {"type": "tool_result", "tool_use_id": tc_id, "content": content_blocks}
                else:
                    output_text = self._extract_text(output_content)
                    block = {"type": "tool_result", "tool_use_id": tc_id, "content": output_text}
                self._merge_anthropic_block(
                    messages, "user", "tool_result", block)
                continue

            # ── function_call → assistant message with tool_use
            if item_type == "function_call":
                # Skip function_calls that have no matching output
                cid = item.get("call_id", "")
                if cid and cid not in output_ids:
                    continue
                args = item.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json_mod.loads(args)
                    except (json_mod.JSONDecodeError, TypeError):
                        args = {}
                block = {
                    "type": "tool_use",
                    "id": item.get("call_id", ""),
                    "name": item.get("name", ""),
                    "input": args,
                }
                self._merge_anthropic_block(
                    messages, "assistant", "tool_use", block)
                continue

            # ── reasoning → inject as thinking block into previous assistant msg
            if item_type == "reasoning":
                reasoning_content = self._extract_text(item.get("content", ""))
                if reasoning_content:
                    thinking_block = {"type": "thinking", "thinking": reasoning_content}
                    # Find last assistant message to attach thinking to
                    for j in range(len(messages) - 1, -1, -1):
                        if messages[j].get("role") == "assistant":
                            c = messages[j].get("content")
                            if isinstance(c, list):
                                c.insert(0, thinking_block)
                            else:
                                messages[j]["content"] = [thinking_block, {"type": "text", "text": c or ""}]
                            break
                continue

            if item_type == "item_reference":
                continue

            # ── regular message
            role = self.ROLE_MAP.get(role, role)
            if role not in self.ALLOWED_ROLES:
                role = "user"
            raw_blocks = self._extract_content_blocks(item.get("content", ""))
            # Convert image blocks to Anthropic format
            content_blocks = []
            for b in raw_blocks:
                if b.get("type") == "image":
                    anthro_img = self._convert_image_to_anthropic(b.get("image_url", ""))
                    if anthro_img:
                        content_blocks.append(anthro_img)
                else:
                    content_blocks.append(b)

            tcs = item.get("tool_calls") or []
            if tcs and role == "assistant":
                text_from_blocks = "".join(
                    b["text"] for b in content_blocks if b.get("type") == "text")
                content_blocks = []
                if text_from_blocks:
                    content_blocks.append({"type": "text", "text": text_from_blocks})
                for tc in tcs:
                    tc_id = tc.get("call_id", tc.get("id", ""))
                    if tc_id and tc_id not in output_ids:
                        continue
                    tc_name = tc.get("function", {}).get(
                        "name", tc.get("name", ""))
                    args = tc.get("function", {}).get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json_mod.loads(args)
                        except (json_mod.JSONDecodeError, TypeError):
                            args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("call_id", tc.get("id", "")),
                        "name": tc_name,
                        "input": args,
                    })
                messages.append(
                    {"role": "assistant", "content": content_blocks})
            else:
                # If no images, keep as plain text for simplicity
                text_only = "".join(
                    b["text"] for b in content_blocks if b.get("type") == "text")
                has_images = any(b.get("type") == "image" for b in content_blocks)
                if has_images:
                    messages.append({"role": role, "content": content_blocks})
                else:
                    messages.append({"role": role, "content": text_only})

        # Ensure every tool_use has a matching tool_result
        self._fix_unmatched_tool_uses(messages)

        model = self._map_model(req.get("model", "deepseek-v4-pro"))
        body = {
            "model": model,
            "messages": messages,
            "stream": req.get("stream", False),
            "max_tokens": req.get("max_output_tokens", 32768),
        }
        if system_parts:
            body["system"] = (system_parts[0] if len(system_parts) == 1
                              else "\n".join(system_parts))
        for k in ("temperature", "top_p",):
            if k in req:
                body[k] = req[k]
        # Reasoning: boolean toggle from model config
        reasoning = req.get("reasoning")
        if reasoning is None:
            from .config import get_active_model_config
            mc = get_active_model_config()
            reasoning = mc.get("reasoning", False) if mc else False
        if reasoning:
            for m in messages:
                if (m.get("role") == "assistant"
                        and isinstance(m.get("content"), list)
                        and any(b.get("type") == "tool_use" for b in m["content"])
                        and not any(b.get("type") == "thinking" for b in m["content"])):
                    m["content"].insert(0, {"type": "thinking", "thinking": ""})
            body["thinking"] = {"type": "enabled", "budget_tokens": 8192}
        tools = req.get("tools", [])
        if tools:
            anthro_tools = self._xlat_tools_anthropic(tools)
            if anthro_tools:
                body["tools"] = anthro_tools
        return body

    @staticmethod
    def _merge_anthropic_block(messages, role, block_type, block):
        check_type = "tool_use" if block_type == "tool_use" else "tool_result"
        if (messages and messages[-1].get("role") == role
                and isinstance(messages[-1].get("content"), list)
                and any(b.get("type") == check_type
                        for b in messages[-1]["content"])):
            messages[-1]["content"].append(block)
        else:
            messages.append({"role": role, "content": [block]})

    @staticmethod
    def _fix_unmatched_tool_uses(messages):
        """Strip tool_use blocks lacking tool_result in the immediate next message."""
        # Pass 1: strip unmatched tool_use and orphaned tool_result in next message
        i = 0
        while i < len(messages):
            m = messages[i]
            if m.get("role") != "assistant" or not isinstance(m.get("content"), list):
                i += 1
                continue
            tu_ids = {b["id"] for b in m["content"] if b.get("type") == "tool_use"}
            if not tu_ids:
                i += 1
                continue
            next_i = i + 1
            tr_ids = set()
            if next_i < len(messages) and messages[next_i].get("role") == "user":
                nc = messages[next_i].get("content")
                if isinstance(nc, list):
                    tr_ids = {b.get("tool_use_id", "") for b in nc if b.get("type") == "tool_result"}
            unmatched = tu_ids - tr_ids
            if unmatched:
                m["content"] = [b for b in m["content"]
                                if not (b.get("type") == "tool_use"
                                        and b.get("id", "") in unmatched)]
                if next_i < len(messages):
                    nc = messages[next_i].get("content")
                    if isinstance(nc, list):
                        messages[next_i]["content"] = [
                            b for b in nc
                            if not (b.get("type") == "tool_result"
                                    and b.get("tool_use_id", "") in unmatched)]
            i += 1

        # Pass 2: globally strip orphaned tool_results (referencing non-existent tool_use)
        all_tu_ids = set()
        for m in messages:
            if isinstance(m.get("content"), list):
                for b in m["content"]:
                    if b.get("type") == "tool_use":
                        all_tu_ids.add(b.get("id", ""))
        for m in messages:
            if isinstance(m.get("content"), list):
                m["content"] = [b for b in m["content"]
                                if not (b.get("type") == "tool_result"
                                        and b.get("tool_use_id", "") not in all_tu_ids)]

        # Remove empty messages
        i = 0
        while i < len(messages):
            content = messages[i].get("content")
            if isinstance(content, list) and len(content) == 0:
                messages.pop(i)
            else:
                i += 1

    @staticmethod
    def _convert_image_to_anthropic(image_url):
        """Convert a data URI or URL to Anthropic image source block."""
        import re as _re
        if not image_url:
            return None
        if image_url.startswith("data:"):
            match = _re.match(r"data:([^;]+);base64,(.+)", image_url)
            if match:
                return {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": match.group(1),
                        "data": match.group(2),
                    }
                }
        # External URL — some providers accept this
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": image_url,
            }
        }

    def _xlat_tools_anthropic(self, tools):
        result = []
        for tool in tools:
            t = tool.get("type", "")
            if t == "web_search":
                result.append({
                    "name": "web_search",
                    "description": "Search the web for current information",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                })
                continue
            if "function" in tool:
                fn = tool["function"]
                result.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get(
                        "parameters", {"type": "object", "properties": {}}),
                })
            elif "name" in tool:
                result.append({
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get(
                        "parameters", {"type": "object", "properties": {}}),
                })
            else:
                result.append({
                    "name": tool.get(
                        "id", f"tool_{_uuid.uuid4().hex[:8]}"),
                    "description": tool.get("description", ""),
                    "input_schema": {"type": "object", "properties": {}},
                })
        return result

    def _from_anthropic_resp(self, anthro_resp):
        import time
        rid = anthro_resp.get("id", self._gid("resp_"))
        mid = self._gid("msg_")
        usage = anthro_resp.get("usage", {})
        output = []

        content_blocks = anthro_resp.get("content", [])
        text_parts = []
        reasoning_text = ""
        for block in content_blocks:
            bt = block.get("type", "")
            if bt == "text":
                text_parts.append(block.get("text", ""))
            elif bt == "thinking":
                reasoning_text += block.get("thinking", "")
            elif bt == "tool_use":
                tc_name = block.get("name", "")
                output.append({
                    "id": self._gid("fc_"),
                    "type": "function_call",
                    "call_id": block.get("id", ""),
                    "name": tc_name,
                    "arguments": json_mod.dumps(
                        block.get("input", {}), ensure_ascii=False),
                })
                if tc_name == "web_search":
                    try:
                        query = block.get("input", {}).get("query", "")
                        from .web_search import search
                        output.append({
                            "id": self._gid("fc_output_"),
                            "type": "function_call_output",
                            "call_id": block.get("id", ""),
                            "output": search(query),
                        })
                    except Exception:
                        pass
        if reasoning_text:
            output.append({
                "id": self._gid("reasoning_"),
                "type": "reasoning",
                "content": reasoning_text,
            })
            # Cache thinking for next turn — keyed by response text
            cache_text = "".join(text_parts)
            if cache_text:
                from .config import _REASONING_CACHE, _REASONING_LOCK
                key = hashlib.sha256(cache_text.encode()).hexdigest()
                with _REASONING_LOCK:
                    _REASONING_CACHE[key] = reasoning_text

        if text_parts:
            output.insert(0, {
                "id": mid, "type": "message", "role": "assistant",
                "content": [{"type": "output_text",
                            "text": "".join(text_parts), "annotations": []}]
            })

        return {
            "id": rid, "object": "response",
            "created_at": int(time.time()),
            "model": anthro_resp.get("model", "unknown"),
            "status": "completed", "output": output,
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": (usage.get("input_tokens", 0)
                                 + usage.get("output_tokens", 0)),
            }
        }

    def _stream_anthropic(self, anthro_req, base_url, api_key):
        resp = self._do_fetch("/messages", anthro_req, base_url, api_key)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        rid = self._gid("resp_")
        text_msg_id = self._gid("msg_")
        started = False
        full_text = ""
        usage_info = {}
        output_items = []
        completed = False
        tool_blocks = {}

        def _finalize():
            nonlocal completed
            if completed:
                return
            completed = True
            usage_info.setdefault("input_tokens", 0)
            usage_info.setdefault("output_tokens", 0)
            usage_info["total_tokens"] = (
                usage_info["input_tokens"] + usage_info["output_tokens"])
            if not started:
                self._sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": rid, "object": "response",
                        "model": anthro_req["model"],
                        "status": "failed", "output": [],
                        "usage": usage_info,
                    }
                })
                try:
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except Exception:
                    pass
                return
            if full_text:
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
                output_items.insert(0, {
                    "id": text_msg_id, "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": full_text,
                                "annotations": []}]
                })
            for idx in sorted(tool_blocks.keys()):
                tb = tool_blocks[idx]
                if not tb.get("_done"):
                    self._sse("response.function_call_arguments.done", {
                        "type": "response.function_call_arguments.done",
                        "item_id": tb["tc_id"], "name": tb["name"],
                        "arguments": tb["input_json"],
                    })
                    self._sse("response.output_item.done", {
                        "type": "response.output_item.done",
                        "item": {"id": tb["tc_id"],
                                 "type": "function_call",
                                 "call_id": tb["tc_id"],
                                 "name": tb["name"],
                                 "arguments": tb["input_json"]}
                    })
                    output_items.append({
                        "id": tb["tc_id"], "type": "function_call",
                        "call_id": tb["tc_id"], "name": tb["name"],
                        "arguments": tb["input_json"]
                    })
            self._sse("response.completed", {
                "type": "response.completed",
                "response": {
                    "id": rid, "object": "response",
                    "model": anthro_req["model"],
                    "status": "completed", "output": output_items,
                    "usage": usage_info,
                }
            })
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass

        try:
            for line in resp:
                raw = line.decode("utf-8").strip()
                if not raw or raw.startswith(":"):
                    continue
                if not raw.startswith("data:"):
                    continue
                data_str = raw[5:]
                event = json_mod.loads(data_str)
                evt = event.get("type", "")

                if evt == "message_start":
                    started = True
                    msg_info = event.get("message", {})
                    usage_info["input_tokens"] = msg_info.get(
                        "usage", {}).get("input_tokens", 0)
                    self._sse("response.created", {
                        "type": "response.created",
                        "response": {"id": rid, "object": "response",
                                     "model": anthro_req["model"],
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

                elif evt == "content_block_start":
                    block = event.get("content_block", {})
                    idx = event.get("index", 0)
                    if block.get("type") == "tool_use":
                        tc_id = block.get("id", self._gid("fc_"))
                        tc_name = block.get("name", "")
                        tool_blocks[idx] = {
                            "tc_id": tc_id, "name": tc_name,
                            "input_json": "", "_done": False}
                        self._sse("response.output_item.added", {
                            "type": "response.output_item.added",
                            "item": {"id": tc_id, "type": "function_call",
                                     "call_id": tc_id, "name": tc_name,
                                     "arguments": ""}
                        })

                elif evt == "content_block_delta":
                    delta = event.get("delta", {})
                    idx = event.get("index", 0)
                    dt = delta.get("type", "")
                    if dt == "text_delta":
                        text = delta.get("text", "")
                        full_text += text
                        self._sse("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "item_id": text_msg_id, "output_index": 0,
                            "content_index": 0, "delta": text,
                        })
                    elif dt == "input_json_delta":
                        partial = delta.get("partial_json", "")
                        if idx in tool_blocks:
                            tool_blocks[idx]["input_json"] += partial
                            self._sse(
                                "response.function_call_arguments.delta", {
                                    "type": "response.function_call_arguments.delta",
                                    "item_id": tool_blocks[idx]["tc_id"],
                                    "delta": partial,
                                })

                elif evt == "content_block_stop":
                    idx = event.get("index", 0)
                    if idx in tool_blocks:
                        tb = tool_blocks[idx]
                        tb["_done"] = True
                        self._sse(
                            "response.function_call_arguments.done", {
                                "type": "response.function_call_arguments.done",
                                "item_id": tb["tc_id"],
                                "name": tb["name"],
                                "arguments": tb["input_json"],
                            })
                        self._sse("response.output_item.done", {
                            "type": "response.output_item.done",
                            "item": {"id": tb["tc_id"],
                                     "type": "function_call",
                                     "call_id": tb["tc_id"],
                                     "name": tb["name"],
                                     "arguments": tb["input_json"]}
                        })
                        output_items.append({
                            "id": tb["tc_id"], "type": "function_call",
                            "call_id": tb["tc_id"], "name": tb["name"],
                            "arguments": tb["input_json"]
                        })

                elif evt == "message_delta":
                    du = (event.get("delta", {}).get("usage", {})
                          or event.get("usage", {}))
                    if du:
                        usage_info["output_tokens"] = du.get(
                            "output_tokens", 0)

                elif evt == "message_stop":
                    usage_info.setdefault("input_tokens", 0)
                    usage_info.setdefault("output_tokens", 0)
                    usage_info["total_tokens"] = (
                        usage_info["input_tokens"]
                        + usage_info["output_tokens"])
                    if full_text:
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
                        output_items.insert(0, {
                            "id": text_msg_id, "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text",
                                         "text": full_text,
                                         "annotations": []}]
                        })
                    self._sse("response.completed", {
                        "type": "response.completed",
                        "response": {
                            "id": rid, "object": "response",
                            "model": anthro_req["model"],
                            "status": "completed",
                            "output": output_items,
                            "usage": usage_info,
                        }
                    })
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    completed = True
        finally:
            _finalize()
