import logging
from abc import ABC, abstractmethod
from typing import Any
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> str:
        ...


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "gpt-4o-mini") -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ImportError("langchain-openai not installed") from e
        self._client = ChatOpenAI(model=model, temperature=0.1, api_key=api_key, base_url=base_url)

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> str:
        response = self._client.invoke(messages, **kwargs)
        return response.content


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022") -> None:
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise ImportError("langchain-anthropic not installed") from e
        self._client = ChatAnthropic(model=model, temperature=0.1, api_key=api_key)

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> str:
        response = self._client.invoke(messages, **kwargs)
        return response.content


class GoogleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise ImportError("langchain-google-genai not installed") from e
        self._client = ChatGoogleGenerativeAI(model=model, temperature=0.1, google_api_key=api_key)

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> str:
        response = self._client.invoke(messages, **kwargs)
        return response.content


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1") -> None:
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            raise ImportError("langchain-ollama not installed") from e
        self._client = ChatOllama(model=model, temperature=0.1, base_url=base_url)

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> str:
        response = self._client.invoke(messages, **kwargs)
        return response.content


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "meta-llama/llama-3.1-70b-instruct") -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ImportError("langchain-openai not installed") from e
        self._client = ChatOpenAI(model=model, temperature=0.1, api_key=api_key, base_url="https://openrouter.ai/api/v1")

    def invoke(self, messages: list[BaseMessage], **kwargs: Any) -> str:
        response = self._client.invoke(messages, **kwargs)
        return response.content


_PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
}


def get_llm_provider(settings: Any) -> LLMProvider:
    provider_name = settings.llm_provider.lower()
    provider_cls = _PROVIDER_MAP.get(provider_name)
    if not provider_cls:
        raise ValueError(f"Unsupported LLM provider: {provider_name}. Choose from {list(_PROVIDER_MAP)}")

    if provider_name == "openai":
        return provider_cls(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
    if provider_name == "anthropic":
        return provider_cls(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    if provider_name == "google":
        return provider_cls(api_key=settings.google_api_key, model=settings.google_model)
    if provider_name == "ollama":
        return provider_cls(base_url=settings.ollama_base_url, model=settings.ollama_model)
    if provider_name == "openrouter":
        return provider_cls(api_key=settings.openrouter_api_key, model=settings.openrouter_model)

    raise ValueError(f"Unsupported LLM provider: {provider_name}")
