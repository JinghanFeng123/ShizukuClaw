from src.graph.state import State
from src.llm.base_client import LLMClient

RESPONSE_SYSTEM_PROMPT = (
    "你是智能助手。基于以下对话上下文和工具执行结果，组织最终回复。\n"
    "工具执行结果：\n{tool_results}\n"
)


class ResponseNode:
    def __init__(self, llm: LLMClient):
        self.name = "ResponseNode"
        self.llm = llm

    def call(self, state: State) -> State:
        tool_results = "\n".join(state.tool_result) if state.tool_result else "(无)"
        try:
            reply = self.llm.chat([
                {"role": "system",
                 "content": RESPONSE_SYSTEM_PROMPT.format(tool_results=tool_results)},
                {"role": "user", "content": state.messages[-1] if state.messages else ""},
            ])
        except Exception as e:
            reply = f"[ResponseNode] LLM 调用失败: {e}"
        state.add_message(reply)
        print(f"[{self.name}] 回复: {reply}")
        return state
