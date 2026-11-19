import logging

import httpx
from google import genai

from app.services.ai_providers.base import (
    AIProviderError,
    AIProviderResult,
)
from app.services.settings import settings

logger = logging.getLogger(__name__)


RETRYABLE_STATUS_CODES = {
    408, 429, 500, 502, 503, 504
}


class GeminiProvider:
    name = "gemini"

    def __init__(self):
        self.model = settings.gemini_model

    def generate(self, prompt: str) -> AIProviderResult:
        if not settings.gemini_api_key:
            raise AIProviderError(
                "Gemini API key is not configured."
            )

        try:
            client = genai.Client(
                api_key=settings.gemini_api_key
            )

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "max_output_tokens": 1500,
                    "candidate_count": 1,
                    "automatic_continuation": False,
                    "response_mime_type": "application/json",
                },
            )

            content = response.text

            if not content:
                raise AIProviderError(
                    "Gemini returned an empty response.",
                    retryable=True,
                )

            return AIProviderResult(
                content=content,
                provider=self.name,
                model=self.model,
            )

        except AIProviderError:
            raise

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(
                "Gemini network failure: %s",
                str(exc),
            )

            raise AIProviderError(
                "Gemini network request failed.",
                retryable=True,
            ) from exc

        except Exception as exc:
            logger.error(
                "Gemini provider request failed: exception_type=%s",
                type(exc).__name__,
            )

            response = getattr(exc, "response", None)

            status_code = (
                getattr(response, "status_code", None)
                or getattr(exc, "status_code", None)
                or getattr(exc, "code", None)
            )

            try:
                status_code = int(status_code) if status_code is not None else None
            except (TypeError, ValueError):
                status_code = None

            retryable = status_code in RETRYABLE_STATUS_CODES

            raise AIProviderError(
                message="Gemini API request failed.",
                retryable=retryable,
                status_code=status_code,
            ) from exc
    async def generate_async(self, prompt: str) -> AIProviderResult:
        """Generate with Gemini's async client so request cancellation propagates."""
        if not settings.gemini_api_key:
            raise AIProviderError("Gemini API key is not configured.")
        client = genai.Client(api_key=settings.gemini_api_key)
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": 0.2,
                    "max_output_tokens": 1500,
                    "candidate_count": 1,
                    "automatic_continuation": False,
                    "response_mime_type": "application/json",
                },
            )
            content = response.text
            if not content:
                raise AIProviderError("Gemini returned an empty response.", retryable=True)
            return AIProviderResult(content=content, provider=self.name, model=self.model)
        except AIProviderError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AIProviderError("Gemini network request failed.", retryable=True) from exc
        except Exception as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None) or getattr(exc, "status_code", None) or getattr(exc, "code", None)
            try:
                status_code = int(status_code) if status_code is not None else None
            except (TypeError, ValueError):
                status_code = None
            raise AIProviderError("Gemini API request failed.", retryable=status_code in RETRYABLE_STATUS_CODES, status_code=status_code) from exc
        finally:
            try:
                await client.aio.aclose()
            except Exception:
                pass

