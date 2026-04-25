from abc import ABC, abstractmethod
from askdata.config import get_settings

settings = get_settings()


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


def get_llm_provider() -> LLMProvider:
    if settings.llm_provider == "gigachat":
        from askdata.query.llm.gigachat import GigaChatProvider
        return GigaChatProvider()
    elif settings.llm_provider == "claude":
        from askdata.query.llm.claude import ClaudeProvider
        return ClaudeProvider()
    else:
        from askdata.query.llm.local import LocalLLMProvider
        return LocalLLMProvider()


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = get_llm_provider()
    return _provider
