from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent.agent_graph import get_agent_graph
from app.config import settings
from app.mcp_manager import get_mcp_manager
from app.paths import DATA_DIR, STATIC_DIR
from app.persona_store import (
    activate_persona as store_activate_persona,
    active_filename,
    delete_persona as store_delete_persona,
    list_personas as store_list_personas,
    load_persona,
    persona_id,
    save_persona,
)
from app.plugin_manager import get_plugin_manager
from app.skill_install import install_from_payload
from app.skill_manager import get_skill_manager
from app.storage.adapter import get_storage

router = APIRouter()
PAGE_MAP = {
    "control_panel": "control_panel.html",
    "sandbox": "chat-sandbox.html",
    "security-init": "security-init.html",
    "logs": "logs.html",
    "monitoring": "monitoring.html",
    "config_editor": "config_editor.html",
    "db_management": "db_management.html",
    "db_console": "db_management.html",
    "diagnosis": "diagnosis.html",
    "adapter_console": "adapter_console.html",
    "adapter_logs": "adapter_logs.html",
    "terminal_chat": "terminal_chat.html",
}


def _page(name: str) -> FileResponse:
    filename = PAGE_MAP.get(name, name)
    path = STATIC_DIR / filename
    if not path.exists():
        path = STATIC_DIR / "control_panel.html"
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


def _persona_filename(name: str) -> str:
    text = str(name or "").strip()
    return text if text.endswith(".json") else f"{text}.json"


@router.get("/")
async def index():
    return _page("control_panel")


@router.get("/control_panel")
async def control_panel():
    return _page("control_panel")


@router.get("/sandbox")
async def sandbox():
    return _page("sandbox")


@router.get("/security-init")
async def security_init():
    return _page("security-init")


@router.get("/logs")
async def logs_page():
    return _page("logs")


@router.get("/monitoring")
async def monitoring_page():
    return _page("monitoring")


@router.get("/config_editor")
async def config_editor():
    return _page("config_editor")


@router.get("/db_management")
@router.get("/db_console")
async def db_page():
    return _page("db_management")


@router.get("/diagnosis")
async def diagnosis_page():
    return _page("diagnosis")


@router.get("/adapter_console")
async def adapter_console():
    return _page("adapter_console")


@router.get("/adapter_logs")
async def adapter_logs_page():
    return _page("adapter_logs")


@router.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()
    message = str(data.get("message") or "").strip()
    if not message and not data.get("image") and not data.get("attachments"):
        return JSONResponse({"success": False, "error": "无效请求"}, status_code=400)
    persona = persona_id(data.get("persona_filename") or data.get("persona") or active_filename())
    result = get_agent_graph().invoke(
        message,
        persona=persona,
        image=data.get("image"),
        attachments=data.get("attachments"),
    )
    debug = {
        "engine": result.get("engine"),
        "persona": result.get("persona"),
        "show_back_to_top": True,
        "trace": result.get("trace") or [],
    }
    if data.get("stream"):
        reply = str(result.get("reply") or "")

        def event_stream():
            yield _sse("meta", {"stage": "start"})
            chunk_size = 24
            for index in range(0, len(reply), chunk_size):
                yield _sse("delta", {"text": reply[index : index + chunk_size]})
            yield _sse("done", {"reply": reply, "debug": debug})

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return {"success": True, "reply": result.get("reply") or "", "debug": debug}


@router.get("/api/personas")
async def list_personas():
    return store_list_personas()


@router.get("/api/personas/{filename}")
async def get_persona(filename: str):
    data = load_persona(filename)
    if not data:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return data


@router.post("/api/personas")
async def create_persona(payload: dict[str, Any]):
    filename = str(payload.get("filename") or "custom.json")
    content = payload.get("content") or {}
    saved = save_persona(filename, content)
    return {"success": True, "filename": saved}


@router.post("/api/personas/activate")
async def activate_persona(payload: dict[str, Any]):
    filename = payload.get("filename") or payload.get("persona_filename") or ""
    try:
        active = store_activate_persona(str(filename))
    except FileNotFoundError:
        return JSONResponse({"error": f"persona not found: {filename}"}, status_code=404)
    return {"success": True, "active": active}


@router.delete("/api/personas/{filename}")
async def delete_persona(filename: str):
    ok = store_delete_persona(filename)
    return {"success": ok}


@router.get("/api/personas/open-folder")
async def open_persona_folder():
    from app.paths import PERSONAS_DIR
    import os
    import sys
    import subprocess

    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(PERSONAS_DIR))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(PERSONAS_DIR)])
        else:
            subprocess.Popen(["xdg-open", str(PERSONAS_DIR)])
    except Exception:
        pass
    return {"success": True, "path": "plugins/personas"}


@router.get("/api/security/status")
async def security_status():
    security = settings.get("security", {}) or {}
    work = settings.get("work_mode", {}) or {}
    return {
        "ok": True,
        "global_admin_enabled": bool(work.get("enabled")),
        "level1_configured": bool(security.get("level1_password_hash")),
        "level2_configured": bool(security.get("level2_password_hash")),
        "sandbox_mode": "local",
        "platform": "windows",
        "has_docker": False,
        "has_wsl": False,
        "chat_settings": _chat_settings(),
    }


def _chat_settings() -> dict[str, Any]:
    work = settings.get("work_mode") or {}
    current = work.get("chat_settings") or {}
    return {
        "sandbox_show_agent_trace": bool(current.get("sandbox_show_agent_trace", True)),
        "sandbox_trace_collapsed": bool(current.get("sandbox_trace_collapsed", True)),
        "sandbox_show_back_to_top": bool(current.get("sandbox_show_back_to_top", True)),
        "deepseek_thinking_mode": bool(current.get("deepseek_thinking_mode", False)),
        "deepseek_reasoning_effort": str(current.get("deepseek_reasoning_effort") or "high"),
        "voice_reply_enabled": bool(current.get("voice_reply_enabled", False)),
    }


def _tts_settings() -> dict[str, Any]:
    chat = _chat_settings()
    tts = settings.get("tts") or {}
    return {
        "success": True,
        "voice_reply_enabled": bool(chat.get("voice_reply_enabled")),
        "tts_enabled": bool(tts.get("enabled", True)),
        "auto_start": bool(tts.get("auto_start", False)),
        "api_base": tts.get("api_base") or "",
        "service_online": False,
        "detail": "TTS service is optional in remake",
        "ref_audio_exists": False,
        "ref_audio_path": tts.get("ref_audio_path") or "",
        "target_language": tts.get("target_language") or "ja",
        "lang_label": tts.get("lang_label") or "日本語",
        "languages": [
            {"code": "ja", "label": "日本語"},
            {"code": "zh", "label": "中文"},
            {"code": "en", "label": "English"},
        ],
    }


@router.post("/api/security/authenticate/level1")
@router.post("/api/security/authenticate/level2")
async def security_auth(payload: dict[str, Any] | None = None):
    return {"ok": True, "session_id": "local-dev", "level": 1, "message": "Authentication skipped in remake"}


@router.get("/api/sandbox/external_approvals")
async def sandbox_approvals():
    return {"success": True, "items": []}


@router.post("/api/sandbox/external_approvals/{request_id}")
@router.post("/api/sandbox/open_path")
@router.post("/api/sandbox/open_url")
@router.post("/api/sandbox/execute")
async def sandbox_actions():
    return {"success": True}


@router.get("/api/chat_settings/deepseek_thinking")
async def get_thinking_mode():
    chat = _chat_settings()
    effort = str(chat.get("deepseek_reasoning_effort") or "high").lower()
    if effort not in {"high", "max"}:
        effort = "high"
    return {
        "success": True,
        "thinking_mode": bool(chat.get("deepseek_thinking_mode")),
        "reasoning_effort": effort,
    }


@router.post("/api/chat_settings/deepseek_thinking")
async def set_thinking_mode(payload: dict[str, Any] | None = None):
    data = payload or {}
    enable = bool(data.get("enable", False))
    effort = str(data.get("reasoning_effort") or "high").lower()
    if effort not in {"high", "max"}:
        effort = "high"
    work = dict(settings.get("work_mode") or {})
    chat = dict(work.get("chat_settings") or {})
    chat["deepseek_thinking_mode"] = enable
    chat["deepseek_reasoning_effort"] = effort
    work["chat_settings"] = chat
    settings.update({"work_mode": work})
    return {
        "success": True,
        "thinking_mode": enable,
        "reasoning_effort": effort,
        "message": f"思考模式已{'启用' if enable else '禁用'}",
    }


@router.get("/api/tts/settings")
async def get_tts_settings():
    return _tts_settings()


@router.post("/api/tts/settings")
async def set_tts_settings(payload: dict[str, Any] | None = None):
    data = payload or {}
    enabled = bool(data.get("voice_reply_enabled", False))
    work = dict(settings.get("work_mode") or {})
    chat = dict(work.get("chat_settings") or {})
    chat["voice_reply_enabled"] = enabled
    work["chat_settings"] = chat
    settings.update({"work_mode": work, "tts": {**(settings.get("tts") or {}), "enabled": enabled}})
    result = _tts_settings()
    result["voice_reply_enabled"] = enabled
    result["tts"] = settings.get("tts") or {}
    return result


@router.get("/api/tts/status")
async def tts_status(autostart: int = 0, persona_filename: str = ""):
    result = _tts_settings()
    result["service_online"] = False
    result["autostart"] = bool(autostart)
    result["persona_filename"] = persona_filename or ""
    return result


@router.post("/api/tts/start")
async def tts_start():
    return {"success": True, "message": "TTS 未接入独立服务，开关已保存"}


@router.get("/api/tts/languages")
async def tts_languages():
    cfg = _tts_settings()
    return {
        "success": True,
        "languages": cfg["languages"],
        "current": cfg["target_language"],
        "current_label": cfg["lang_label"],
    }


@router.get("/api/plugins/status")
async def plugins_status():
    return {"success": True, "status": get_plugin_manager().get_framework_status()}


@router.post("/api/plugins/reload")
async def plugins_reload():
    get_plugin_manager().reload()
    return {"success": True, "status": get_plugin_manager().get_framework_status(), "message": "Plugin framework reloaded"}


@router.post("/api/plugins/policy")
async def plugins_policy(payload: dict[str, Any]):
    name = str(payload.get("plugin_name") or "").strip()
    if not name:
        return JSONResponse({"success": False, "error": "plugin_name is required"}, status_code=400)
    try:
        policy = get_plugin_manager().update_policy(name, payload.get("policy") or {})
    except KeyError:
        return JSONResponse({"success": False, "error": f"plugin not found: {name}"}, status_code=404)
    return {"success": True, "plugin_name": name, "policy": policy}


@router.get("/api/plugins/config")
@router.post("/api/plugins/config")
async def plugins_config(plugin_name: str | None = None, payload: dict[str, Any] | None = None):
    return {"success": True, "plugin_name": plugin_name or (payload or {}).get("plugin_name"), "config": {}}


@router.get("/api/plugins/ui-extensions")
@router.get("/api/plugins/ui-extensions/menu")
@router.get("/api/plugins/ui-extensions/pages")
@router.get("/api/plugins/ui-extensions/settings")
@router.get("/api/plugins/ui-extensions/widgets")
async def plugin_ui_extensions():
    return {"success": True, "extensions": [], "items": []}


@router.get("/api/systems/tasks")
@router.post("/api/systems/tasks")
@router.get("/api/systems/knowledge")
@router.get("/api/systems/knowledge/entries")
@router.get("/api/systems/instructions")
@router.get("/api/systems/system-status")
async def systems_stub():
    return {
        "success": True,
        "code": 0,
        "data": [],
        "items": [],
        "tasks": [],
        "status": {"ok": True, "storage": get_storage().status()},
    }


@router.get("/api/systems/plugins")
async def systems_plugins():
    plugins = get_plugin_manager().list_plugins()
    return {"success": True, "code": 0, "data": plugins}


@router.get("/api/systems/skills")
async def systems_skills():
    skills = get_skill_manager().list_skills()
    return {"success": True, "code": 0, "data": skills}


@router.get("/api/systems/mcp")
@router.get("/api/systems/mcp/servers")
async def systems_mcp():
    servers = get_mcp_manager().list_servers()
    return {"success": True, "code": 0, "data": servers}


@router.post("/api/systems/mcp/servers")
async def create_mcp_server(payload: dict[str, Any]):
    server = get_mcp_manager().upsert(payload)
    return {"success": True, "code": 0, "data": server.__dict__}


@router.get("/api/systems/mcp/servers/{server_id}")
async def get_mcp_server(server_id: str):
    for item in get_mcp_manager().list_servers():
        if item.get("id") == server_id:
            return {"success": True, "code": 0, "data": item}
    return JSONResponse({"success": False, "code": 1, "message": "not found"}, status_code=404)


@router.delete("/api/systems/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    ok = get_mcp_manager().delete(server_id)
    return {"success": ok, "code": 0 if ok else 1}


@router.get("/api/systems/mcp/market/smithery/status")
@router.get("/api/systems/mcp/market/smithery/search")
async def mcp_market(page: int = 1, page_size: int = 24, query: str = ""):
    return {
        "success": True,
        "code": 0,
        "data": {"installed": False, "cli": "", "version": "", "mode": "missing"},
        "page": page,
        "page_size": page_size,
        "total": 0,
        "has_more": False,
    }


@router.post("/api/systems/mcp/market/smithery/cli/install")
@router.get("/api/systems/mcp/market/smithery/cli/install/jobs/{job_id}")
async def smithery_cli(job_id: str = "local"):
    return {
        "success": True,
        "code": 0,
        "message": "Smithery CLI 未内置，请按官方文档安装",
        "data": {
            "mode": "guide",
            "installed": False,
            "job_id": job_id,
            "status": "success",
            "docs_url": "https://smithery.ai",
            "logs": ["Smithery CLI is optional in remake."],
        },
    }


@router.get("/api/systems/dify/market/cli/status")
@router.post("/api/systems/dify/market/cli/install")
@router.get("/api/systems/dify/market/cli/install/jobs/{job_id}")
async def dify_cli(job_id: str = "local"):
    return {
        "success": True,
        "code": 0,
        "message": "success",
        "data": {
            "installed": False,
            "cli": "",
            "version": "",
            "mode": "missing",
            "docs_url": "https://docs.dify.ai/zh/develop-plugin/getting-started/cli",
            "job_id": job_id,
            "status": "success",
            "logs": ["Dify CLI is optional in remake."],
        },
    }


@router.post("/api/skills/market/skillhub/cli/install")
@router.get("/api/skills/market/skillhub/cli/install/jobs/{job_id}")
async def skillhub_cli(job_id: str = "local"):
    return {
        "success": True,
        "installed": False,
        "cli": "",
        "version": "",
        "mode": "missing",
        "job_id": job_id,
        "status": "success",
        "logs": ["SkillHub CLI is optional in remake."],
        "message": "SkillHub CLI 未内置，本地 Skill 已可直接加载",
    }


@router.post("/api/systems/knowledge/entries")
@router.get("/api/systems/knowledge/entries/{entry_id}")
@router.post("/api/systems/knowledge/entries/{entry_id}")
@router.delete("/api/systems/knowledge/entries/{entry_id}")
async def knowledge_entries(entry_id: str = ""):
    return {"success": True, "code": 0, "data": [], "id": entry_id}


@router.get("/api/systems/personalities")
@router.post("/api/systems/personalities")
async def systems_personalities(payload: dict[str, Any] | None = None):
    items = store_list_personas().get("personas") or []
    return {"success": True, "code": 0, "data": items}


@router.get("/api/skills/market/github")
@router.get("/api/skills/market/skillhub/search")
@router.get("/api/skills/market/cocoloop")
async def market_search(page: int = 1, page_size: int = 24, query: str = ""):
    items = []
    for skill in get_skill_manager().list_skills():
        name = str(skill.get("name") or skill.get("skill_id") or "")
        desc = str(skill.get("description") or "")
        if query and query.lower() not in f"{name} {desc}".lower():
            continue
        items.append(
            {
                "id": skill.get("skill_id"),
                "name": name,
                "description": desc,
                "external_url": "",
                "source": "local",
            }
        )
    start = max(page - 1, 0) * page_size
    sliced = items[start : start + page_size]
    return {
        "success": True,
        "code": 0,
        "items": sliced,
        "data": sliced,
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "has_more": start + page_size < len(items),
        "diagnostics": {"cache": {"count": len(items), "age_seconds": 0}, "sources": [{"source": "local", "ok": True, "count": len(items)}], "errors": []},
    }


@router.get("/api/skills/market/skillhub/status")
async def skillhub_status():
    return {"success": True, "installed": False, "cli": "", "version": "", "mode": "local"}


@router.get("/api/systems/dify/market/search")
async def dify_market(page: int = 1, page_size: int = 24, query: str = ""):
    return {"success": True, "code": 0, "data": [], "page": page, "page_size": page_size, "total": 0, "has_more": False}


@router.post("/api/skills/market/github/install")
@router.post("/api/skills/market/cocoloop/install")
@router.post("/api/skills/market/skillhub/install")
@router.post("/api/skills/market/agent-deploy")
async def market_install(payload: dict[str, Any]):
    result = install_from_payload(payload)
    result["message"] = f"Skill 已安装: {result.get('skill_id')}"
    result["job_id"] = result.get("skill_id")
    result["status"] = "success"
    return result


@router.get("/api/skills/market/agent-deploy/jobs/{job_id}")
async def market_install_job(job_id: str):
    return {"success": True, "job_id": job_id, "status": "success"}


@router.post("/api/skills/upload")
async def skills_upload(payload: dict[str, Any] | None = None):
    result = install_from_payload(payload or {})
    result["message"] = f"Skill 已加载: {result.get('skill_id')}"
    return result


@router.delete("/api/systems/tasks/{task_id}")
async def delete_task(task_id: str):
    return {"success": True, "id": task_id}


@router.get("/api/gateway/diagnose")
async def gateway_diagnose():
    return {"success": True, "adapter": {"models": True}, "message": "remake gateway ready"}


@router.post("/api/database/query")
async def database_query():
    return {"success": True, "rows": get_storage().list_records(limit=50)}


@router.post("/api/run_mode")
async def run_mode():
    return {"success": True}


@router.get("/api/realtime_search/subscriptions")
@router.post("/api/realtime_search/subscriptions")
@router.get("/api/realtime_search/updates")
async def realtime_search_stub():
    return {"success": True, "items": []}


@router.delete("/api/realtime_search/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    return {"success": True}


@router.post("/api/work_mode/password")
@router.post("/api/work_mode/options")
@router.post("/api/work_mode/reset_password_terminal")
async def work_mode_stub():
    return {"success": True}


@router.get("/api/status")
async def api_status():
    graph = get_agent_graph()
    return {
        "status": "ShizukuClaw Remake Backend Running",
        "version": "1.0.0",
        "docs": "/docs",
        "storage": get_storage().status(),
        "persona": graph.default_persona(),
        "skills": get_skill_manager().list_skills(),
        "mcp": get_mcp_manager().list_servers(),
    }


def mount_static(app) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _sse(event_name: str, payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_name}\ndata: {body}\n\n"
