from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.paths import PLUGINS_DIR, ensure_runtime_dirs


@dataclass
class PluginMeta:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    project_path: str = ""
    policy: dict[str, Any] = field(default_factory=dict)
    hooks: list[str] = field(default_factory=list)


class PluginManager:
    def __init__(self, plugins_dir: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.plugins_dir = plugins_dir or PLUGINS_DIR
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, PluginMeta] = {}
        self._enabled = True
        self.reload()

    def reload(self) -> dict[str, PluginMeta]:
        self._plugins.clear()
        for manifest in sorted(self.plugins_dir.rglob("plugin.json")):
            if "mcp" in manifest.parts and manifest.parent.name == "mcp":
                continue
            if "skills" in manifest.parts:
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                continue
            name = str(data.get("name") or manifest.parent.name)
            self._plugins[name] = PluginMeta(
                name=name,
                version=str(data.get("version") or "0.1.0"),
                description=str(data.get("description") or ""),
                author=str(data.get("author") or ""),
                dependencies=list(data.get("dependencies") or []),
                project_path=str(manifest.parent.relative_to(self.plugins_dir).as_posix()),
                policy=self._default_policy(data.get("policy") or {}),
                hooks=list(data.get("hooks") or []),
            )
        if "core.local" not in self._plugins:
            self._plugins["core.local"] = PluginMeta(
                name="core.local",
                version="1.0.0",
                description="Remake 核心插件：聊天、人格、记忆、本地存储",
                author="ShizukuClaw",
                project_path="core",
                policy=self._default_policy({}),
                hooks=["chat", "memory"],
            )
        return self._plugins

    def _default_policy(self, incoming: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": bool(incoming.get("enabled", True)),
            "allow_network": bool(incoming.get("allow_network", False)),
            "max_execution_ms": int(incoming.get("max_execution_ms", 10000) or 10000),
            "allowed_domains": list(incoming.get("allowed_domains") or []),
            "allowed_commands": list(incoming.get("allowed_commands") or []),
        }

    def list_plugins(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self._plugins.values()]

    def get_framework_status(self) -> dict[str, Any]:
        plugins = self.list_plugins()
        return {
            "enabled": self._enabled,
            "loaded_plugins": [item["name"] for item in plugins],
            "plugins": plugins,
            "commands": [],
            "degraded": False,
        }

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def update_policy(self, plugin_name: str, policy: dict[str, Any]) -> dict[str, Any]:
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise KeyError(plugin_name)
        plugin.policy = self._default_policy({**plugin.policy, **policy})
        return plugin.policy


_PLUGIN_MANAGER: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _PLUGIN_MANAGER
    if _PLUGIN_MANAGER is None:
        _PLUGIN_MANAGER = PluginManager()
    return _PLUGIN_MANAGER
