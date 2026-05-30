#!/usr/bin/env python3
"""LLM 接口抽象层 — 统一所有大模型调用

支持：
  - DeepSeek (默认)
  - 任意 OpenAI-compatible API
  - 本地模型 / 自定义适配器

用法：
    from llm_interface import LLMInterface, DeepSeekAdapter

    llm = DeepSeekAdapter(api_key="...")
    text = llm.generate("你好")
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import json, os, time
from urllib.request import urlopen, Request
from urllib.error import HTTPError


class LLMInterface(ABC):
    """LLM 接口抽象基类。所有需要大模型的节点都通过此接口调用。"""

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> str:
        """
        生成文本。

        Args:
            prompt: 用户提示词
            max_tokens: 最大输出长度
            temperature: 温度（0=确定，1=创意）
            system_prompt: 系统提示词（可选）

        Returns:
            生成的文本字符串
        """
        pass

    def batch_generate(self, prompts: List[str], max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> List[str]:
        """
        批量生成。默认串行实现，子类可覆盖为并行/并发。

        Args:
            prompts: 提示词列表
            max_tokens, temperature, system_prompt: 同 generate()

        Returns:
            按顺序返回生成的文本列表
        """
        results = []
        for i, p in enumerate(prompts):
            if i > 0 and (i % 5) == 0:
                time.sleep(1)  # 默认速率限制保护
            results.append(self.generate(p, max_tokens, temperature, system_prompt))
        return results

    def generate_json(self, prompt: str, max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> dict:
        """
        生成并解析为JSON。失败时返回 {}。
        """
        text = self.generate(prompt, max_tokens, temperature, system_prompt).strip()
        # 尝试提取 {...} 或 [...]
        if text.startswith("```json"):
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # 尝试找第一个 { 或 [
            for start_char in ["{", "["]:
                idx = text.find(start_char)
                if idx >= 0:
                    try:
                        # 找匹配的结尾
                        if start_char == "{":
                            # 简单方式：找最后一个 }
                            end_idx = text.rfind("}")
                            if end_idx > idx:
                                return json.loads(text[idx:end_idx+1])
                        else:
                            end_idx = text.rfind("]")
                            if end_idx > idx:
                                return json.loads(text[idx:end_idx+1])
                    except (json.JSONDecodeError, ValueError):
                        continue
            return {}


class DeepSeekAdapter(LLMInterface):
    """DeepSeek API 适配器（默认）"""

    def __init__(self, api_key: str = None, model: str = "deepseek-chat"):
        self.api_key = api_key or self._load_key()
        self.model = model
        self.base_url = "https://api.deepseek.com/v1/chat/completions"

    def _load_key(self) -> str:
        for p in ["./.env", os.path.join(os.path.dirname(__file__), ".env")]:
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("DEEPSEEK_API_KEY="):
                            return line.split("=", 1)[1].strip().strip('"')
            except (OSError, IOError):
                pass
        return os.environ.get("DEEPSEEK_API_KEY", "")

    def generate(self, prompt: str, max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        req = Request(self.base_url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })

        for attempt in range(3):
            try:
                with urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
                    return data["choices"][0]["message"]["content"].strip()
            except HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return ""


class OpenAICompatibleAdapter(LLMInterface):
    """任意 OpenAI-compatible API 适配器"""

    def __init__(self, api_key: str, base_url: str, model: str = "gpt-4"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") + "/chat/completions"
        self.model = model

    def generate(self, prompt: str, max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

        req = Request(self.base_url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })

        for attempt in range(3):
            try:
                with urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
                    return data["choices"][0]["message"]["content"].strip()
            except HTTPError as e:
                if e.code == 429 and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return ""


class LocalMockAdapter(LLMInterface):
    """本地模拟适配器（不调用LLM，用于快速测试/离线）"""

    def __init__(self, echo: bool = False):
        self.echo = echo

    def generate(self, prompt: str, max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> str:
        if self.echo:
            return f"[MOCK] {prompt[:80]}..."
        return "{\"result\": \"mock\"}"

    def batch_generate(self, prompts: List[str], max_tokens: int = 3000, temperature: float = 0, system_prompt: str = "") -> List[str]:
        return [self.generate(p, max_tokens, temperature, system_prompt) for p in prompts]


def create_llm(adapter: str = "deepseek", **kwargs) -> LLMInterface:
    """
    工厂函数：按名称创建LLM适配器。

    Args:
        adapter: "deepseek" | "openai" | "mock"
        **kwargs: 适配器特定参数

    Returns:
        LLMInterface 实例
    """
    if adapter == "deepseek":
        return DeepSeekAdapter(**kwargs)
    elif adapter == "openai":
        return OpenAICompatibleAdapter(**kwargs)
    elif adapter == "mock":
        return LocalMockAdapter(**kwargs)
    raise ValueError(f"Unknown adapter: {adapter}")


if __name__ == "__main__":
    # 快速测试
    llm = LocalMockAdapter(echo=True)
    print(llm.generate("测试"))
    print("LLM接口层 OK")
