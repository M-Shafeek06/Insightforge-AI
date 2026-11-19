from dataclasses import dataclass
from typing import Protocol


@dataclass
class AIProviderResult:
    content: str
    provider: str
    model: str


class AIProviderError(Exception):
    def __init__(
        self,
        message: str,
        retryable: bool = False,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class AIProvider(Protocol):
    name: str
    model: str

    def generate(self, prompt: str) -> AIProviderResult:
        ...