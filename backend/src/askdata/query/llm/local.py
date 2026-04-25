import httpx
from askdata.query.llm.provider import LLMProvider
from askdata.config import get_settings

settings = get_settings()


class LocalLLMProvider(LLMProvider):
    async def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        seed: int | None = None,
    ) -> str:
        payload = {
            "model": settings.local_llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 512,
        }
        if seed is not None:
            payload["seed"] = seed

        headers = {"Content-Type": "application/json"}
        if settings.local_llm_api_key:
            headers["Authorization"] = f"Bearer {settings.local_llm_api_key}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.local_llm_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    async def is_available(self) -> bool:
        try:
            headers = {}
            if settings.local_llm_api_key:
                headers["Authorization"] = f"Bearer {settings.local_llm_api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.local_llm_url}/models",
                    headers=headers,
                )
                return resp.status_code == 200
        except Exception:
            return False
