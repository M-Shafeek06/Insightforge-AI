import httpx

from app.services.ai_providers.base import (
    AIProviderError,
    AIProviderResult,
)
from app.services.settings import settings


class GroqProvider:
    name = "groq"

    def __init__(self):
        self.model = settings.groq_model

    def generate(self, prompt: str) -> AIProviderResult:
        if not settings.groq_api_key:
            raise AIProviderError(
                "Groq API key is not configured."
            )

        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "response_format": {
                "type": "json_object"
            },
            "temperature": 0.2,
            "max_completion_tokens": 1500,
        }

        try:
            with httpx.Client(
                timeout=settings.ai_provider_timeout_seconds
            ) as client:
                response = client.post(
                    url,
                    headers=headers,
                    json=payload,
                )

            if response.status_code >= 400:
                retryable = response.status_code in {
                    408, 429, 500, 502, 503, 504
                }

                raise AIProviderError(
                    message=f"Groq API request failed with HTTP {response.status_code}.",
                    retryable=retryable,
                    status_code=response.status_code,
                )

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise AIProviderError(
                    "Groq returned a malformed response.",
                    retryable=True,
                    status_code=response.status_code,
                ) from exc

            if not content:
                raise AIProviderError(
                    "Provider returned an empty response.",
                    retryable=True,
                )
            return AIProviderResult(
                content=content,
                provider=self.name,
                model=self.model,
            )

        except httpx.TimeoutException as exc:
            raise AIProviderError(
                "Groq request timed out.",
                retryable=True,
            ) from exc

        except httpx.RequestError as exc:
            raise AIProviderError(
                "Groq network request failed.",
                retryable=True,
            ) from exc

    async def generate_async(self, prompt: str) -> AIProviderResult:
        """Async Groq request; cancellation closes the in-flight HTTP request."""
        if not settings.groq_api_key:
            raise AIProviderError("Groq API key is not configured.")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.groq_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_completion_tokens": 1500,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ai_provider_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                retryable = response.status_code in {408, 429, 500, 502, 503, 504}
                raise AIProviderError(f"Groq API request failed with HTTP {response.status_code}.", retryable=retryable, status_code=response.status_code)
            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise AIProviderError("Groq returned a malformed response.", retryable=True, status_code=response.status_code) from exc
            if not content:
                raise AIProviderError("Provider returned an empty response.", retryable=True)
            return AIProviderResult(content=content, provider=self.name, model=self.model)
        except httpx.TimeoutException as exc:
            raise AIProviderError("Groq request timed out.", retryable=True) from exc
        except httpx.RequestError as exc:
            raise AIProviderError("Groq network request failed.", retryable=True) from exc

