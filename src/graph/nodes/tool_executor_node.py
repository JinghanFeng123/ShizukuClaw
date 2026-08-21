import json
import re

from src.graph.state import State
from src.llm.base_client import LLMClient
from src.tools.registry import ToolRegistry

TOOL_SYSTEM_PROMPT = (
    "你是工具调用器。根据用户需求判断是否需要调用工具。\n"
    "工具列表如下（JSON）：\n{tools}\n"
    "如果需要调用工具，只输出一个 JSON："
    '{{"name": "工具名", "arguments": {{...参数...}}}}\n'
    "如果不需要调用工具，只输出：NONE\n"
    "不要输出其他内容。"
)


class ToolExecutorNode:
    def __init__(self, llm: LLMClient, registry: ToolRegistry):
        self.name = "ToolExecutorNode"
        self.llm = llm
        self.registry = registry

    def call(self, state: State) -> State:
        state.memory["tool_called"] = False
        tools_json = json.dumps(self.registry.get_schemas(), ensure_ascii=False)

        last_msg = state.messages[-1] if state.messages else ""
        try:
            reply = self.llm.chat([
                {"role": "system", "content": TOOL_SYSTEM_PROMPT.format(tools=tools_json)},
                {"role": "user", "content": last_msg},
            ])
        except Exception as e:
            print(f"[{self.name}] LLM 调用失败: {e}")
            return state

        tool_call = self._parse_tool_call(reply)
        if tool_call is None:
            print(f"[{self.name}] 未检测到工具调用")
            return state

        name, arguments = tool_call
        print(f"[{self.name}] 调用工具: {name}({arguments})")
        try:
            result = self.registry.execute(name, arguments)
        except (ValueError, KeyError) as e:
            result = f"Error: {e}"
        state.tool_result.append(f"[{name}] {arguments} -> {result}")
        state.memory["tool_called"] = True
        print(f"[{self.name}] 结果: {result}")
        return state

    @staticmethod
    def _parse_tool_call(reply: str) -> tuple[str, dict] | None:
        """从 LLM 回复中解析工具调用，兼容 {name, arguments} 与 OpenAI {function} 两种格式"""
        if "NONE" in reply.strip().upper():
            return None
        try:
            data = json.loads(reply)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", reply, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        if isinstance(data, dict) and "function" in data:  # OpenAI tool_call 格式
            fn = data["function"]
            arguments = json.loads(fn.get("arguments", "{}"))
            return fn.get("name", ""), arguments
        if isinstance(data, dict) and "name" in data:
            return data["name"], data.get("arguments", {})
        return None
