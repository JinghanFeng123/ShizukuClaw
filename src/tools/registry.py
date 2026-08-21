from src.tools.base_tool import Tool

"""
    用于登记工具的类
"""

class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        """返回所有已注册工具的 OpenAI 格式声明，用于传给 LLM"""
        return [tool.get_schema() for tool in self.tools.values()]

    def execute(self, name: str, args: dict) -> str:
        if name not in self.tools:
            raise  ValueError(f"Tool {name} not found")
        return self.tools[name].run(args)
