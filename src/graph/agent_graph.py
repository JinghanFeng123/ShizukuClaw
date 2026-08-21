from src.graph.nodes.response_node import ResponseNode
from src.graph.nodes.router_node import RouterNode
from src.graph.nodes.tool_executor_node import ToolExecutorNode
from src.graph.state import State
from src.graph.visualizer import visualize_graph
from src.llm.base_client import LLMClient
from src.tools.registry import ToolRegistry


class AgentGraph:
    """
    图结构（与 UML 图一致）：
    Start -> RouterNode -> (intent=tool) ToolExecutorNode -+-> ResponseNode -> End
                            |                               |(循环, 最多 max_rounds 轮)
                            +---------> (intent=answer) ----+
    """

    def __init__(self, llm: LLMClient, registry: ToolRegistry, max_rounds: int = 10):
        self.llm = llm
        self.registry = registry
        self.max_rounds = max_rounds
        self.nodes: dict[str, object] = {}

    def build(self) -> AgentGraph:
        # 构建节点并注入依赖（依赖注入：LLM 与 ToolRegistry 由外部传入）
        self.nodes = {
            "RouterNode": RouterNode(self.llm),
            "ToolExecutorNode": ToolExecutorNode(self.llm, self.registry),
            "ResponseNode": ResponseNode(self.llm),
        }
        print("Building Graph...")
        return self

    def invoke(self, input_data: dict) -> State:
        current_state = State(**input_data)

        # 遍历：Router -> ToolExecutor -> Router ... 或 Router -> Response
        for _ in range(self.max_rounds):
            current_state = self.nodes["RouterNode"].call(current_state)
            if current_state.intent != "tool":
                break  # 直接回答，进入 ResponseNode
            current_state = self.nodes["ToolExecutorNode"].call(current_state)
            if not current_state.memory.get("tool_called"):
                break  # LLM 最终未调用工具，不再循环

        current_state = self.nodes["ResponseNode"].call(current_state)
        return current_state

    def visualize(self, path: str | None = "graph.png") -> bytes:
        """渲染图为 PNG 字节：Notebook 中通过 IPython.display 内联展示，否则保存到 path"""
        return visualize_graph(self.registry, path=path, max_rounds=self.max_rounds)
