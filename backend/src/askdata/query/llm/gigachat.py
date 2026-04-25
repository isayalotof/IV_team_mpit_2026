import asyncio
from askdata.query.llm.provider import LLMProvider
from askdata.config import get_settings

settings = get_settings()

_ROLE_MAP = None


def _get_role_map():
    global _ROLE_MAP
    if _ROLE_MAP is None:
        from gigachat.models import MessagesRole
        _ROLE_MAP = {
            "system": MessagesRole.SYSTEM,
            "user": MessagesRole.USER,
            "assistant": MessagesRole.ASSISTANT,
        }
    return _ROLE_MAP


class GigaChatProvider(LLMProvider):
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from gigachat import GigaChat
            self._client = GigaChat(
                credentials=settings.gigachat_credentials,
                verify_ssl_certs=False,
                scope="GIGACHAT_API_PERS",
            )
        return self._client

    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> str:
        from gigachat.models import Chat, Messages
        role_map = _get_role_map()
        client = self._get_client()

        gc_messages = [
            Messages(
                role=role_map.get(m["role"], role_map["user"]),
                content=m["content"],
            )
            for m in messages
        ]

        response = await asyncio.to_thread(
            client.chat,
            Chat(
                messages=gc_messages,
                temperature=temperature,
                model=settings.gigachat_model,
            ),
        )
        return response.choices[0].message.content.strip()

    async def is_available(self) -> bool:
        if not settings.gigachat_credentials:
            return False
        try:
            await self.generate([{"role": "user", "content": "SELECT 1"}], temperature=0.0)
            return True
        except Exception:
            return False
