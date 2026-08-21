from dataclasses import dataclass, field
from typing import Any


@dataclass
class State:
    """
    messages: 对话上下文
    intent: 路由决策标签
    tool_result: 工具调用返还的结果
    memory: 存储那些不属于上述三类，但在流程中需要跨节点传递的临时数据或元数据。
    """
    messages: list[str] = field(default_factory=list)
    intent: str = ""
    tool_result: list[str] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)

    def add_message(self, msg: str):
        self.messages.append(msg)
