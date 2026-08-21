from src.graph.state import State
from src.llm.base_client import LLMClient

# 无 LLM 可用时的关键词兜底：命中文件操作类词汇 → 需要工具
TOOL_KEYWORDS = ("文件", "目录", "查看", "创建", "删除", "复制", "移动", "重命名",
                 "ls", "dir", "cat", "mkdir", "cp", "mv", "rm", "list", "文件夹")

ROUTER_SYSTEM_PROMPT = (
    "你是路由决策器。判断用户意图，只输出一个词：\n"
    "- 如果用户需要操作文件/目录（查看、创建、删除、复制、移动、重命名等），输出 TOOL\n"
    "- 如果任务已完成或无需工具，输出 ANSWER\n"
    "已有的工具执行结果（若任务已完成则选择 ANSWER）：\n{tool_results}\n"
    "不要输出其他内容。"
)


class RouterNode:
    def __init__(self, llm: LLMClient):
        self.name = "RouterNode"
        self.llm = llm

    def call(self, state: State) -> State:
        """调用 LLM 判断意图，并写入 state.intent（tool / answer）"""
        state.intent = self.route(state)
        print(f"[{self.name}] intent = {state.intent}")
        return state

    def route(self, state: State) -> str:
        last_msg = state.messages[-1] if state.messages else ""
        tool_results = "\n".join(state.tool_result) if state.tool_result else "(无)"
        try:
            reply = self.llm.chat([
                {"role": "system",
                 "content": ROUTER_SYSTEM_PROMPT.format(tool_results=tool_results)},
                {"role": "user", "content": last_msg},
            ]).strip().upper()
            if "TOOL" in reply:
                return "tool"
            if "ANSWER" in reply:
                return "answer"
            # LLM 有回复但无法解析，落到关键词兜底
        except Exception as e:
            print(f"[{self.name}] LLM 调用失败，使用关键词兜底: {e}")
        # 兜底：LLM 不可用或返回无法解析时，按关键词判断
        if any(kw in last_msg.lower() for kw in TOOL_KEYWORDS):
            return "tool"
        return "answer"
