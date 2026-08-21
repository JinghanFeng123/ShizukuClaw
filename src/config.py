import os
import yaml
from dataclasses import dataclass, field

@dataclass
class Config:
    # UML 定义的三个核心字段, 此处系初始化默认值
    llm_provider: str = "openai"  # 默认值
    model_name: str = "gpt-3.5-turbo"  # 默认值
    max_rounds: int = 10  # 默认值
    api_key: str = ""
    system_prompt: str = "You are a helpful assistant."
    temperature: float = 0.7

    def __init__(self, config_path: str = "config/settings.yaml"):
        """
        初始化配置：
        1. 从 YAML 文件加载默认值
        2. 从环境变量覆盖敏感信息（如 API Key）
        """
        self._load_from_yaml(config_path)
        self._load_from_env()


    def _load_from_yaml(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if data:
                # 映射 YAML 结构到类属性
                llm_conf = data.get('llm', {})
                self.llm_provider = llm_conf.get('provider', self.llm_provider)
                self.model_name = llm_conf.get('model_name', self.model_name)
                self.temperature = llm_conf.get('temperature', self.temperature)

                agent_conf = data.get('agent', {})
                self.max_rounds = agent_conf.get('max_rounds', self.max_rounds)
                self.system_prompt = agent_conf.get('system_prompt', self.system_prompt)

        except FileNotFoundError:
            print(f"[Warning] Config file {path} not found. Using defaults.")

    def _load_from_env(self):
        """优先从环境变量读取敏感信息"""
        # 假设环境变量名为 OPENAI_API_KEY
        self.api_key = os.getenv("OPENAI_API_KEY", "")



if __name__ == "__main__":
    config = Config()
    print(config.llm_provider)
    print(config.model_name)
    print(config.max_rounds)
    print(config.api_key)