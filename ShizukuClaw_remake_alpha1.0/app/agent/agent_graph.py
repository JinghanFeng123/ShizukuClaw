from __future__ import annotations

from typing import Any

from app.agent.loop import get_agent_loop


class AgentGraph:
    """Compatibility wrapper. Runtime is the traditional tool-loop agent."""

    def __init__(self) -> None:
        self._loop = get_agent_loop()

    def available_personas(self) -> list[dict[str, Any]]:
        return self._loop.available_personas()

    def default_persona(self) -> str:
        return self._loop.default_persona()

    def invoke(
        self,
        message: str,
        persona: str | None = None,
        thread_id: str | None = None,
        image: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._loop.invoke(
            message,
            persona=persona,
            thread_id=thread_id,
            image=image,
            attachments=attachments,
        )


_GRAPH: AgentGraph | None = None


def get_agent_graph() -> AgentGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = AgentGraph()
    return _GRAPH
