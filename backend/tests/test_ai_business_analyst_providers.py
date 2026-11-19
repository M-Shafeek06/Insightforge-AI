import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.services import ai_business_analyst as analyst
from app.services.ai_providers.base import AIProviderError, AIProviderResult
from app.services.settings import settings


VALID = {
    "refined_objective": "Analyze sales performance by region.",
    "business_questions": ["Which region has the highest sales?"],
    "reasoning_summary": "Region and Sales columns support this comparison.",
    "recommended_focus_areas": ["Regional sales comparison"],
    "clarifying_questions": [],
}


def test_groq_is_used_when_gemini_fails(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")
    monkeypatch.setattr(settings, "groq_api_key", "groq-test")
    monkeypatch.setattr(settings, "ai_fallback_enabled", True)

    gemini = MagicMock()
    gemini.name = "gemini"
    gemini.generate.side_effect = AIProviderError("temporary", retryable=True)
    groq = MagicMock()
    groq.name = "groq"
    groq.generate.return_value = AIProviderResult(json.dumps(VALID), "groq", "test-model")

    monkeypatch.setattr(analyst, "GeminiProvider", lambda: gemini)
    monkeypatch.setattr(analyst, "GroqProvider", lambda: groq)

    result = analyst.generate_business_analysis(
        "Analyze sales by region", [],
        [{"name": "Region", "dtype": "object"}, {"name": "Sales", "dtype": "float64"}],
        100,
    )
    assert result == VALID
    gemini.generate.assert_called_once()
    groq.generate.assert_called_once()


def test_groq_only_when_gemini_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", "groq-test")
    monkeypatch.setattr(settings, "ai_fallback_enabled", True)
    groq = MagicMock()
    groq.name = "groq"
    groq.generate.return_value = AIProviderResult(json.dumps(VALID), "groq", "test-model")
    monkeypatch.setattr(analyst, "GroqProvider", lambda: groq)

    assert analyst.generate_business_analysis("Analyze sales", [], [], 10) == VALID
    groq.generate.assert_called_once()


def test_invalid_gemini_json_falls_back_to_groq(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")
    monkeypatch.setattr(settings, "groq_api_key", "groq-test")
    monkeypatch.setattr(settings, "ai_fallback_enabled", True)
    gemini = MagicMock()
    gemini.name = "gemini"
    gemini.generate.return_value = AIProviderResult('{"invented": true}', "gemini", "test-model")
    groq = MagicMock()
    groq.name = "groq"
    groq.generate.return_value = AIProviderResult(json.dumps(VALID), "groq", "test-model")
    monkeypatch.setattr(analyst, "GeminiProvider", lambda: gemini)
    monkeypatch.setattr(analyst, "GroqProvider", lambda: groq)

    assert analyst.generate_business_analysis("Analyze sales", [], [], 10) == VALID
    groq.generate.assert_called_once()


def test_no_configured_provider_returns_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "groq_api_key", None)
    with pytest.raises(RuntimeError, match="No AI provider is configured"):
        analyst.generate_business_analysis("Analyze sales", [], [], 10)
