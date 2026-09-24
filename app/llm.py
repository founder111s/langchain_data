"""LLM 工厂：OpenAI 兼容接口统一接入（可选启用 LangSmith 可观测性）。"""
import os

from langchain_openai import ChatOpenAI

from app.config import settings


def configure_langsmith() -> bool:
    """若配置了 LANGSMITH_API_KEY，则将环境变量注入进程以启用 LangSmith 追踪。

    LangChain 1.x 通过环境变量（LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT）
    自动启用追踪，无需手动挂 callback。返回是否已启用。
    """
    if settings.langsmith_api_key and settings.langchain_tracing_v2:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_TRACING_V2", "true")
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        return True
    return False


def get_llm(temperature: float = 0.1, model: str | None = None) -> ChatOpenAI:
    """返回 OpenAI 兼容 Chat 模型。

    通过 OPENAI_BASE_URL 支持 DeepSeek / Qwen / OpenAI / vLLM / Ollama 等任意兼容端点；
    未显式配置 API Key 时回退到环境变量 OPENAI_API_KEY。
    """
    return ChatOpenAI(
        model=model or settings.openai_model,
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key or None,
        temperature=temperature,
    )