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
    "groq": OpenAIProvider,
}


def get_llm_provider(settings: Any, user_config: Any | None = None) -> LLMProvider:
    if user_config is not None:
        if hasattr(user_config, "model_dump"):
            user_config = user_config.model_dump()
        provider_name = str(user_config.get("provider", "openai")).lower()
        api_key = str(user_config.get("api_key", ""))
        model = str(user_config.get("model", ""))
        base_url = str(user_config.get("base_url", ""))
        if provider_name != "ollama" and not api_key:
            raise ValueError("Add your API key in AI settings before using this provider.")
        default_models = {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-20241022",
            "google": "gemini-2.0-flash",
            "ollama": "llama3.1",
            "openrouter": "meta-llama/llama-3.1-70b-instruct",
            "groq": "openai/gpt-oss-20b",
        }
        model = model or default_models.get(provider_name, "")
        provider_cls = _PROVIDER_MAP.get(provider_name)
        if not provider_cls:
            raise ValueError(f"Unsupported AI provider: {provider_name}")
        if provider_name == "openai":
            return provider_cls(api_key=api_key, base_url=base_url or "https://api.openai.com/v1", model=model)
        if provider_name == "groq":
            return provider_cls(api_key=api_key, base_url=base_url or "https://api.groq.com/openai/v1", model=model)
        if provider_name == "anthropic":
            return provider_cls(api_key=api_key, model=model)
        if provider_name == "google":
            return provider_cls(api_key=api_key, model=model)
        if provider_name == "ollama":
            return provider_cls(base_url=base_url or "http://localhost:11434", model=model)
        if provider_name == "openrouter":
            return OpenRouterProvider(api_key=api_key, model=model)

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
