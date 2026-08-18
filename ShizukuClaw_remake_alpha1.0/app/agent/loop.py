from __future__ import annotations

import os
from typing import Any

from app.agent.tools import OPENAI_TOOLS, model_supports_vision, parse_tool_arguments, run_tool
from app.config import settings
from app.persona_store import active_filename, build_system_prompt, list_personas, load_persona, persona_id
from app.storage.adapter import get_storage

MAX_TOOL_ROUNDS = 6
IMAGE_HINT = "不要调用 read_file 去读 png/jpg/gif/webp。"


class AgentLoop:
    def __init__(self) -> None:
        self.storage = get_storage()

    def default_persona(self) -> str:
        return persona_id(active_filename())

    def available_personas(self) -> list[dict[str, Any]]:
        return list_personas().get("personas") or []

    def invoke(
        self,
        message: str,
        persona: str | None = None,
        thread_id: str | None = None,
        image: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        current = persona_id(persona) if persona else self.default_persona()
        thread = thread_id or f"persona:{current}"
        checkpoint = self.storage.load_checkpoint(thread, current) or {"messages": []}
        history = list(checkpoint.get("messages") or [])
        user_content = self._compose_user_content(message, None, None)
        extras = []
        if image or _collect_images(image, attachments):
            extras.append("用户发了图片，当前模型按纯文本处理，已忽略图片内容。")
        for item in attachments or []:
            name = str(item.get("name") or item.get("filename") or "attachment")
            extras.append(f"[附件: {name}]")
        if extras:
            user_content = "\n".join([str(user_content)] + extras).strip()
        history.append({"role": "user", "content": user_content})
        history[:] = [_sanitize_history(item) for item in history]
        memories = self.storage.search_memories(message or current, persona=current, top_k=5)
        memory_text = "\n".join(f"- {item.get('content')}" for item in memories) or "暂无长期记忆。"
        persona_data = load_persona(f"{current}.json") or {}
        prompt = build_system_prompt(persona_data)
        work = settings.get("work_mode") or {}
        if work.get("enabled"):
            prompt += "\n\n[工作模式] 允许执行文件与工具操作，但仍按当前人格说话。"
        else:
            prompt += "\n\n[娱乐模式] 不要执行危险系统操作，以当前人格正常聊天。"
        prompt += "\n\n不要读取或提及图片文件。"
        reply, traces, engine = self._run_loop(prompt, memory_text, history, current, vision=False)
        history.append({"role": "assistant", "content": reply})
        self.storage.save_checkpoint(thread, current, {"messages": history[-40:]})
        self.storage.add_chat_record(current, "user", message or _content_to_text(user_content))
        self.storage.add_chat_record(current, "assistant", reply)
        if message and len(message) >= 12:
            self.storage.add_memory(current, message, kind="long_term")
        return {
            "success": True,
            "persona": current,
            "reply": reply,
            "memory": memories,
            "engine": engine,
            "trace": traces,
        }

    def _compose_user_content(
        self,
        message: str,
        image: str | None,
        attachments: list[dict[str, Any]] | None,
    ) -> Any:
        text = (message or "").strip()
        images = _collect_images(image, attachments)
        if not images:
            extras = []
            for item in attachments or []:
                name = str(item.get("name") or item.get("filename") or "attachment")
                extras.append(f"[附件: {name}]")
            if extras:
                return "\n".join([text] + extras).strip() or "（空消息）"
            return text or "（空消息）"
        parts: list[dict[str, Any]] = [{"type": "text", "text": text or "请查看这张图片。"}]
        for url in images:
            parts.append({"type": "image_url", "image_url": {"url": url}})
        return parts

    def _run_loop(
        self,
        prompt: str,
        memory_text: str,
        history: list[dict[str, Any]],
        persona: str,
        vision: bool = False,
    ) -> tuple[str, list[dict[str, Any]], str]:
        api_key = settings.get("llm", {}).get("api_key") or os.getenv("OPENAI_API_KEY") or ""
        if not api_key:
            last_user = next((item.get("content") for item in reversed(history) if item.get("role") == "user"), "")
            reply = (
                f"[{persona}] 已收到：{_content_to_text(last_user)}\n"
                "当前运行传统 Agent 循环。未配置主模型 API Key，因此使用本地回退回复。\n"
                f"相关记忆：{memory_text}"
            )
            return reply, [], "local-fallback"

        try:
            from openai import OpenAI
        except Exception as exc:
            return f"[{persona}] 无法加载 OpenAI 客户端：{exc}", [], "error"

        client = OpenAI(
            api_key=api_key,
            base_url=settings.get("llm", {}).get("base_url") or None,
        )
        model = settings.get("llm", {}).get("model") or "gpt-4o-mini"
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"{prompt}\n\n[长期记忆]\n{memory_text}\n\n"
                    "你是传统工具循环 Agent：需要外部信息时先调用工具，再根据工具结果回答。"
                    f"{IMAGE_HINT}"
                ),
            }
        ]
        outgoing = [_sanitize_history(item) for item in history[-12:]]
        messages.extend(outgoing)
        traces: list[dict[str, Any]] = []
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                completion = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    temperature=0.4,
                )
            except Exception as exc:
                err = str(exc).lower()
                if "does not support image" not in err and "image input" not in err:
                    raise
                messages[:] = [_sanitize_history(item) for item in messages]
                try:
                    completion = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=OPENAI_TOOLS,
                        temperature=0.4,
                    )
                except Exception:
                    return "当前模型不能看图，已跳过图片相关内容。请用文字描述。", traces, "no-vision"
            choice = completion.choices[0].message
            tool_calls = list(choice.tool_calls or [])
            if not tool_calls:
                return (choice.content or "").strip(), traces, "tool-loop"
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": choice.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments or "{}",
                        },
                    }
                    for call in tool_calls
                ],
            }
            messages.append(assistant_msg)
            for call in tool_calls:
                args = parse_tool_arguments(call.function.arguments)
                result = run_tool(call.function.name, args, persona)
                image_url = ""
                tool_text = result
                if isinstance(result, dict) and result.get("__image_url__"):
                    image_url = str(result.get("__image_url__") or "")
                    tool_text = str(result.get("note") or "已用主模型多模态加载图片。")
                traces.append({"tool": call.function.name, "args": args, "result": str(tool_text)[:500]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": tool_text,
                    }
                )
                if image_url and vision:
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "请直接查看这张刚读取的图片并回答。"},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    )
        return "工具调用轮次过多，已停止。请把问题拆小后再试。", traces, "tool-loop-limit"


def _collect_images(image: str | None, attachments: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    if image:
        urls.append(str(image))
    for item in attachments or []:
        name = str(item.get("name") or item.get("filename") or "")
        kind = str(item.get("type") or item.get("mime") or "")
        content = item.get("content") or item.get("url") or item.get("data") or ""
        is_image = "image" in kind.lower() or name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))
        if is_image and content:
            urls.append(str(content))
    return urls


def _strip_images(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, list):
        cleaned = dict(message)
        cleaned["content"] = _content_to_text(content) or "（空消息）"
        return cleaned
    if isinstance(content, str) and "data:image" in content:
        cleaned = dict(message)
        cleaned["content"] = "[图片已忽略]"
        return cleaned
    return message


def _sanitize_history(message: dict[str, Any]) -> dict[str, Any]:
    cleaned = _strip_images(message)
    content = str(cleaned.get("content") or "")
    if "does not support image" in content.lower() or "image input" in content.lower() or "__image_url__" in content:
        cleaned = dict(cleaned)
        cleaned["content"] = "（已忽略不支持的图片内容）"
    return cleaned


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(str(part.get("text") or ""))
            elif isinstance(part, dict) and part.get("type") == "image_url":
                texts.append("[图片]")
        return "\n".join(item for item in texts if item) or "[多模态消息]"
    return str(content or "")


_LOOP: AgentLoop | None = None


def get_agent_loop() -> AgentLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = AgentLoop()
    return _LOOP
