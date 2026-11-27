"""Pure OpenAI chat/Responses translation and SSE normalization.

This module deliberately has no HTTP client, Compose, or lifecycle state. The
gateway keeps compatibility wrappers for these functions in ``main`` so
existing callers and focused tests retain their import path.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import HTTPException


def merge_system_prefix(prefix: str, content: Any) -> Any:
    if isinstance(content, list):
        return [{"type": "text", "text": prefix}] + list(content)
    if content is None:
        return prefix
    return f"{prefix}\n{content}"


def longwriter_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project the conversation onto the first message LongWriter consumes."""
    turns = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif (
                    isinstance(part, dict)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                ):
                    parts.append(part["text"])
                else:
                    raise HTTPException(status_code=400, detail="LongWriter accepts only text message parts")
            content = "\n".join(parts)
        if len(messages) == 1 and role == "user" and isinstance(content, str):
            return [{**message, "content": content}]
        if isinstance(content, str) and content:
            turns.append(f"[{role}]\n{content}")

    if not turns:
        return messages
    return [{"role": "user", "content": "\n\n".join(turns)}]


def rewrite_messages(model: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body["model"] = model["backend_model"]
    prefix = model.get("default_system_prefix") or ""
    if prefix:
        messages = list(body.get("messages", []))
        first = messages[0] if messages else None
        if isinstance(first, dict) and first.get("role") == "system":
            merged = dict(first)
            merged["content"] = merge_system_prefix(prefix, first.get("content"))
            messages[0] = merged
        else:
            messages.insert(0, {"role": "system", "content": prefix})
        body["messages"] = messages
    if model.get("id") == "longwriter-zero-32b":
        if isinstance(body.get("messages"), list):
            body["messages"] = longwriter_messages(body["messages"])
        body.setdefault("stop", ["</answer>"])
    return body


def responses_content_to_chat(content: Any) -> Any:
    if isinstance(content, str) or content is None:
        return content or ""
    if not isinstance(content, list):
        return str(content)
    parts: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            parts.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"}:
            parts.append({"type": "text", "text": str(part.get("text") or "")})
        elif part_type in {"input_image", "image_url"}:
            image_url = part.get("image_url") or part.get("url")
            if isinstance(image_url, str):
                image_url = {"url": image_url}
            if isinstance(image_url, dict):
                parts.append({"type": "image_url", "image_url": image_url})
    if len(parts) == 1 and parts[0].get("type") == "text":
        return parts[0]["text"]
    return parts


def responses_input_to_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": responses_content_to_chat(instructions)})
    items = body.get("input", "")
    if isinstance(items, str):
        messages.append({"role": "user", "content": items})
        return messages
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Responses input must be text or a list")
    for item in items:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role")
        if role in {"system", "developer", "user", "assistant"}:
            messages.append({"role": "system" if role == "developer" else role, "content": responses_content_to_chat(item.get("content"))})
        elif item_type == "function_call":
            messages.append({"role": "assistant", "content": "", "tool_calls": [{
                "id": item.get("call_id") or item.get("id") or str(uuid.uuid4()),
                "type": "function",
                "function": {"name": item.get("name"), "arguments": item.get("arguments") or "{}"},
            }]})
        elif item_type == "function_call_output":
            messages.append({"role": "tool", "tool_call_id": item.get("call_id") or item.get("id"), "content": responses_content_to_chat(item.get("output"))})
    return messages


def responses_tools_to_chat(tools: Any) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return converted
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        if isinstance(tool.get("function"), dict):
            converted.append(tool)
            continue
        function = {"name": tool.get("name"), "description": tool.get("description") or "", "parameters": tool.get("parameters") or {"type": "object", "properties": {}}}
        if "strict" in tool:
            function["strict"] = bool(tool["strict"])
        converted.append({"type": "function", "function": function})
    return converted


def responses_to_chat_body(body: dict[str, Any]) -> dict[str, Any]:
    chat: dict[str, Any] = {"model": body.get("model"), "messages": responses_input_to_messages(body), "stream": False}
    for key in ("temperature", "top_p", "parallel_tool_calls", "seed", "user"):
        if key in body:
            chat[key] = body[key]
    if "max_output_tokens" in body:
        chat["max_tokens"] = body["max_output_tokens"]
    elif "max_tokens" in body:
        chat["max_tokens"] = body["max_tokens"]
    tools = responses_tools_to_chat(body.get("tools"))
    if tools:
        chat["tools"] = tools
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        chat["tool_choice"] = {"type": "function", "function": {"name": tool_choice.get("name")}}
    elif isinstance(tool_choice, str) and tool_choice in {"auto", "none", "required"}:
        chat["tool_choice"] = tool_choice
    text_format = (body.get("text") or {}).get("format")
    if isinstance(text_format, dict) and text_format.get("type") in {"json_object", "json_schema"}:
        chat["response_format"] = text_format
    return chat


def content_is_empty(content: Any) -> bool:
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        texts = [part if isinstance(part, str) else str(part.get("text") or "") for part in content if isinstance(part, (str, dict))]
        return not "".join(texts).strip()
    return False


def chat_to_responses(payload: dict[str, Any], requested_model: str, response_id: str | None = None) -> dict[str, Any]:
    response_id = response_id or f"resp_{uuid.uuid4().hex}"
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    output: list[dict[str, Any]] = []
    content = message.get("content")
    if not content_is_empty(content):
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        output.append({"id": f"msg_{uuid.uuid4().hex}", "type": "message", "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": content, "annotations": []}]})
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        output.append({"id": f"fc_{uuid.uuid4().hex}", "type": "function_call", "status": "completed", "call_id": call.get("id") or f"call_{uuid.uuid4().hex}", "name": function.get("name"), "arguments": arguments})
    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    created_at = int(payload.get("created") or time.time())
    return {"id": response_id, "object": "response", "created_at": created_at, "completed_at": int(time.time()), "status": "completed", "error": None, "incomplete_details": None, "instructions": None, "model": requested_model, "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": [], "temperature": None, "top_p": None, "usage": {"input_tokens": input_tokens, "input_tokens_details": {"cached_tokens": 0}, "output_tokens": output_tokens, "output_tokens_details": {"reasoning_tokens": 0}, "total_tokens": int(usage.get("total_tokens") or input_tokens + output_tokens)}}


def flatten_reasoning_into_content(payload: Any) -> Any:
    """Keep private reasoning separate from user-visible assistant content.

    The compatibility helper remains in place for callers and imports, but a
    reasoning-only response must not be promoted into ``content``: clients
    such as voice/TTS may speak ``content`` directly.
    """
    if not isinstance(payload, dict):
        return payload
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return payload
    # ``reasoning_content`` is an opt-in/private channel. Preserve it as
    # supplied and never copy it into visible or spoken content.
    return payload


def flatten_sse_line(line: bytes) -> bytes:
    raw = line.rstrip(b"\r\n")
    suffix = line[len(raw):]
    if not raw.startswith(b"data:"):
        return line
    data = raw[5:].lstrip()
    if data == b"[DONE]" or not data:
        return line
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return line
    flatten_reasoning_into_content(payload)
    return b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8") + suffix


async def iter_flattened_sse(chunks: AsyncIterator[bytes], *, flatten_reasoning: bool = True) -> AsyncIterator[bytes]:
    buffer = bytearray()
    async for chunk in chunks:
        buffer.extend(chunk)
        while True:
            idx = buffer.find(b"\n")
            if idx < 0:
                break
            line = bytes(buffer[:idx + 1])
            del buffer[:idx + 1]
            yield flatten_sse_line(line) if flatten_reasoning else line
    if buffer:
        yield flatten_sse_line(bytes(buffer)) if flatten_reasoning else bytes(buffer)
