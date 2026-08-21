from abc import ABC, abstractmethod


class Tool(ABC):
    def __init__(
        self,
        name: str,
        description: str = "",
        parameters: dict | None = None,
    ):
        self.name = name
        self.description = description
        # 参数的 JSON Schema（OpenAI 工具调用格式），用于约束 LLM 生成合法参数
        self.parameters = parameters or {"type": "object", "properties": {}}

    def get_schema(self) -> dict:
        """返回 OpenAI 格式的工具声明，注册后传给 LLM 供其决定何时调用"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    @abstractmethod
    def run(self, args: dict) -> str:
        pass
