from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable

from app.paths import DATA_DIR
from app.storage.adapter import get_storage

WORKSPACE = DATA_DIR / "workspace"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff"}


def _safe_path(raw: str) -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    target = (WORKSPACE / str(raw or "").lstrip("/\\")).resolve()
    root = WORKSPACE.resolve()
    if root != target and root not in target.parents:
        raise ValueError("path escapes workspace")
    return target


def tool_list_dir(path: str = ".") -> str:
    target = _safe_path(path)
    if not target.exists():
        return f"目录不存在: {path}"
    if not target.is_dir():
        return f"不是目录: {path}"
    items = []
    for child in sorted(target.iterdir()):
        mark = "/" if child.is_dir() else ""
        items.append(f"{child.name}{mark}")
    return "\n".join(items) or "(空目录)"


def encode_image_data_url(path: str | Path) -> str:
    target = path if isinstance(path, Path) else _safe_path(path)
    suffix = target.suffix.lower().lstrip(".") or "png"
    if suffix == "jpg":
        suffix = "jpeg"
    raw = target.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/{suffix};base64,{encoded}"


def model_supports_vision(model: str | None = None) -> bool:
    from app.config import settings

    name = str(model or (settings.get("llm") or {}).get("model") or "").lower()
    vision_hints = (
        "gpt-4o",
        "gpt-4.1",
        "gpt-4-turbo",
        "gpt-4-vision",
        "gpt-5",
        "claude-3",
        "claude-sonnet",
        "claude-opus",
        "gemini",
        "qwen-vl",
        "qwen2-vl",
        "qwen2.5-vl",
        "glm-4v",
    )
    return any(hint in name for hint in vision_hints)


def tool_read_file(path: str) -> str | dict[str, Any]:
    target = _safe_path(path)
    if not target.exists():
        return f"文件不存在: {path}"
    if not target.is_file():
        return f"不是文件: {path}"
    if target.suffix.lower() in IMAGE_SUFFIXES:
        if not model_supports_vision():
            return (
                f'Cannot read "{target.name}" with the current text-only model. '
                "Inform the user that this model does not support image input."
            )
        return {
            "__image_url__": encode_image_data_url(target),
            "note": f"已加载图片 {target.name}，请直接用主模型多模态查看。",
        }
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f'Cannot read "{target.name}" (binary file). Inform the user.'
    if len(text) > 12000:
        return text[:12000] + "\n...[truncated]"
    return text


def tool_write_file(path: str, content: str) -> str:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content or "", encoding="utf-8")
    return f"已写入 {path} ({len(content or '')} chars)"


def tool_search_memory(query: str, persona: str = "companion") -> str:
    items = get_storage().search_memories(query or "", persona=persona, top_k=5)
    if not items:
        return "没有找到相关记忆。"
    return "\n".join(f"- {item.get('content')}" for item in items)


def tool_add_memory(content: str, persona: str = "companion") -> str:
    if not content.strip():
        return "记忆内容为空。"
    get_storage().add_memory(persona, content.strip(), kind="long_term")
    return "已写入长期记忆。"


TOOL_IMPLS: dict[str, Callable[..., str]] = {
    "list_dir": tool_list_dir,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "search_memory": tool_search_memory,
    "add_memory": tool_add_memory,
}

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files in the local workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative workspace path"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a workspace file. Images are loaded via the primary model's multimodal vision.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write a text file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_memory",
            "description": "Save a fact to long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
]


def run_tool(name: str, arguments: dict[str, Any], persona: str) -> Any:
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return f"未知工具: {name}"
    kwargs = dict(arguments or {})
    if name in {"search_memory", "add_memory"}:
        kwargs["persona"] = persona
    try:
        return impl(**kwargs)
    except TypeError as exc:
        return f"工具参数错误: {exc}"
    except Exception as exc:
        return f"工具执行失败: {exc}"


def parse_tool_arguments(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
