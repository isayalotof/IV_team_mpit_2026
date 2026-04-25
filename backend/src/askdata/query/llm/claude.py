import anthropic
from askdata.query.llm.provider import LLMProvider
from askdata.config import get_settings

settings = get_settings()


class ClaudeProvider(LLMProvider):
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.claude_api_key)

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> str:
        # Split system message out — Anthropic API takes it separately
        system = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append({"role": m["role"], "content": m["content"]})

        kwargs: dict = {
            "model": settings.claude_model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text.strip()

    async def is_available(self) -> bool:
        return bool(settings.claude_api_key)
