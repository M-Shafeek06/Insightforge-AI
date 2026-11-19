import json
from unittest.mock import MagicMock

import pytest

from app.services.ai_providers.base import AIProviderError, AIProviderResult
from app.services.ai_results_interpreter import interpret_analytics_results
from app.services import ai_results_interpreter as interpreter
from app.services.settings import settings


VALID_INTERPRETATION = {
    "executive_summary": "Sales performance shows measurable variation.",
    "key_findings": [
        {
            "title": "Sales variation",
            "observation": "Sales values vary across the supplied segments.",
            "business_impact": "Performance differs between the observed segments.",
        }
    ],
    "business_implications": ["Segment performance should be monitored."],
    "risks_and_limitations": [
        "Interpretation is limited to the supplied analytical results."
    ],
    "recommendations": [
        {
            "action": "Review segment performance regularly.",
            "rationale": "Monitoring can identify changes in observed performance.",
            "priority": "medium",
        }
    ],
}
VALID_JSON = json.dumps(VALID_INTERPRETATION)


@pytest.fixture
def configure_providers(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini-key")
    monkeypatch.setattr(settings, "groq_api_key", "test-groq-key")
    monkeypatch.setattr(settings, "ai_fallback_enabled", True)

    gemini, groq = MagicMock(), MagicMock()
    gemini.name, gemini.model = "gemini", "test-gemini-model"
    groq.name, groq.model = "groq", "test-groq-model"
    monkeypatch.setattr(interpreter, "GeminiProvider", lambda: gemini)
    monkeypatch.setattr(interpreter, "GroqProvider", lambda: groq)
    return gemini, groq


def execute_interpretation():
    return interpret_analytics_results(
        operation="descriptive",
        request_config={"column": "sales"},
        result={
            "column": "sales",
            "row_count": 4,
            "valid_value_count": 4,
            "null_count": 0,
            "statistics": {
                "mean": 150.0,
                "median": 150.0,
                "minimum": 50.0,
                "maximum": 300.0,
                "standard_deviation": 111.80339887498948,
            },
        },
    )


def successful_result(provider, model):
    return AIProviderResult(content=VALID_JSON, provider=provider, model=model)


def test_gemini_success_prevents_fallback(configure_providers):
    gemini, groq = configure_providers
    gemini.generate.return_value = successful_result("gemini", "test-gemini-model")
    result = execute_interpretation()
    assert result["provider"] == "gemini"
    prompt = gemini.generate.call_args.args[0]
    assert "<analytical_evidence_json>" in prompt
    assert "untrusted data" in prompt.lower()
    gemini.generate.assert_called_once()
    groq.generate.assert_not_called()


def test_gemini_rate_limit_triggers_groq(configure_providers):
    gemini, groq = configure_providers
    gemini.generate.side_effect = AIProviderError("Rate limited", retryable=True, status_code=429)
    groq.generate.return_value = successful_result("groq", "test-groq-model")
    assert execute_interpretation()["provider"] == "groq"
    gemini.generate.assert_called_once()
    groq.generate.assert_called_once()


def test_gemini_authentication_error_still_tries_independent_groq(configure_providers):
    gemini, groq = configure_providers
    gemini.generate.side_effect = AIProviderError("Invalid credentials", retryable=False, status_code=401)
    groq.generate.return_value = successful_result("groq", "test-groq-model")
    assert execute_interpretation()["provider"] == "groq"
    gemini.generate.assert_called_once()
    groq.generate.assert_called_once()


def test_missing_gemini_key_skips_to_groq(configure_providers, monkeypatch):
    gemini, groq = configure_providers
    monkeypatch.setattr(settings, "gemini_api_key", None)
    groq.generate.return_value = successful_result("groq", "test-groq-model")
    assert execute_interpretation()["provider"] == "groq"
    gemini.generate.assert_not_called()
    groq.generate.assert_called_once()


def test_invalid_json_triggers_groq(configure_providers):
    gemini, groq = configure_providers
    gemini.generate.return_value = AIProviderResult(
        content='{"invalid": "structure"}', provider="gemini", model="test-gemini-model"
    )
    groq.generate.return_value = successful_result("groq", "test-groq-model")
    assert execute_interpretation()["provider"] == "groq"
    gemini.generate.assert_called_once()
    groq.generate.assert_called_once()


def test_all_provider_failures_raise_runtime_error(configure_providers):
    gemini, groq = configure_providers
    gemini.generate.side_effect = AIProviderError("Gemini unavailable", retryable=True, status_code=503)
    groq.generate.side_effect = AIProviderError("Groq unavailable", retryable=True, status_code=503)
    with pytest.raises(RuntimeError):
        execute_interpretation()
    gemini.generate.assert_called_once()
    groq.generate.assert_called_once()


def test_disabled_fallback_uses_only_gemini(configure_providers, monkeypatch):
    gemini, groq = configure_providers
    monkeypatch.setattr(settings, "ai_fallback_enabled", False)
    gemini.generate.side_effect = AIProviderError("Gemini unavailable", retryable=True, status_code=503)
    with pytest.raises(RuntimeError):
        execute_interpretation()
    gemini.generate.assert_called_once()
    groq.generate.assert_not_called()


def test_active_provider_chain_contains_only_gemini_and_groq(configure_providers):
    gemini, groq = configure_providers
    gemini.generate.return_value = successful_result("gemini", "test-gemini-model")
    execute_interpretation()
    assert not hasattr(settings, "cerebras_api_key")
    assert not hasattr(interpreter, "CerebrasProvider")
