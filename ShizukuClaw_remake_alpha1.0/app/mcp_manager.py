from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.paths import MCP_DIR, ensure_runtime_dirs


@dataclass
class MCPServer:
    id: str
    name: str
    description: str = ""
    type: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    enabled: bool = True
    status: str = "disconnected"
    tools: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds") + "Z")


class MCPManager:
    def __init__(self, mcp_dir: Path | None = None) -> None:
        ensure_runtime_dirs()
        self.mcp_dir = mcp_dir or MCP_DIR
        self.mcp_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.mcp_dir / "servers.json"
        self._servers: dict[str, MCPServer] = {}
        self.reload()

    def reload(self) -> dict[str, MCPServer]:
        self._servers.clear()
        if self.registry_path.exists():
            try:
                payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
                for item in payload.get("servers", []):
                    server = MCPServer(**item)
                    self._servers[server.id] = server
            except Exception:
                pass
        for config_file in sorted(self.mcp_dir.glob("*.json")):
            if config_file.name == "servers.json":
                continue
            try:
                item = json.loads(config_file.read_text(encoding="utf-8"))
                if "id" not in item:
                    item["id"] = config_file.stem
                server = MCPServer(**{k: v for k, v in item.items() if k in MCPServer.__dataclass_fields__})
                self._servers[server.id] = server
            except Exception:
                continue
        if not self._servers:
            builtin = MCPServer(
                id="local-files",
                name="Local Files",
                description="Local workspace file tools",
                type="internal",
                enabled=True,
                status="connected",
                tools=["read_file", "list_dir", "write_file"],
            )
            self._servers[builtin.id] = builtin
            self._persist()
        return self._servers

    def _persist(self) -> None:
        payload = {"servers": [asdict(item) for item in self._servers.values()]}
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_servers(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self._servers.values()]

    def list_tools(self) -> list[dict[str, Any]]:
        tools = []
        for server in self._servers.values():
            if not server.enabled:
                continue
            for tool in server.tools:
                tools.append({"server": server.id, "name": tool, "status": server.status})
        return tools

    def upsert(self, data: dict[str, Any]) -> MCPServer:
        server_id = str(data.get("id") or data.get("name") or f"mcp-{len(self._servers)+1}")
        current = self._servers.get(server_id)
        merged = asdict(current) if current else {}
        merged.update({k: v for k, v in data.items() if v is not None})
        merged["id"] = server_id
        server = MCPServer(**{k: v for k, v in merged.items() if k in MCPServer.__dataclass_fields__})
        self._servers[server.id] = server
        self._persist()
        return server

    def delete(self, server_id: str) -> bool:
        if server_id not in self._servers:
            return False
        self._servers.pop(server_id, None)
        self._persist()
        return True


_MCP_MANAGER: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _MCP_MANAGER
    if _MCP_MANAGER is None:
        _MCP_MANAGER = MCPManager()
    return _MCP_MANAGER
