import pytest
from pydantic import ValidationError

from app.schemas.ai_interpretation import AIInterpretationContent


VALID_INTERPRETATION = {
    "executive_summary": "Sales performance shows measurable variation.",
    "key_findings": [
        {
            "title": "Sales variation",
            "observation": "Sales values vary across the supplied segments.",
            "business_impact": "Performance differs between the observed segments.",
        }
    ],
    "business_implications": [
        "Segment performance should be monitored."
    ],
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


def test_valid_interpretation_preserves_existing_response_shape():
    parsed = AIInterpretationContent.model_validate(VALID_INTERPRETATION)

    assert parsed.model_dump() == VALID_INTERPRETATION


def test_invalid_recommendation_priority_is_rejected():
    payload = {
        **VALID_INTERPRETATION,
        "recommendations": [
            {
                **VALID_INTERPRETATION["recommendations"][0],
                "priority": "urgent",
            }
        ],
    }

    with pytest.raises(ValidationError):
        AIInterpretationContent.model_validate(payload)


def test_unexpected_top_level_field_is_rejected():
    payload = {
        **VALID_INTERPRETATION,
        "unrequested_metadata": "must not be accepted",
    }

    with pytest.raises(ValidationError):
        AIInterpretationContent.model_validate(payload)


def test_unexpected_nested_finding_field_is_rejected():
    payload = {
        **VALID_INTERPRETATION,
        "key_findings": [
            {
                **VALID_INTERPRETATION["key_findings"][0],
                "fabricated_metric": 123,
            }
        ],
    }

    with pytest.raises(ValidationError):
        AIInterpretationContent.model_validate(payload)


def test_unexpected_recommendation_field_is_rejected():
    payload = {
        **VALID_INTERPRETATION,
        "recommendations": [
            {
                **VALID_INTERPRETATION["recommendations"][0],
                "confidence": 0.99,
            }
        ],
    }

    with pytest.raises(ValidationError):
        AIInterpretationContent.model_validate(payload)


def test_empty_insight_arrays_are_valid_when_evidence_is_insufficient():
    payload = {
        **VALID_INTERPRETATION,
        "key_findings": [],
        "business_implications": [],
        "recommendations": [],
    }
    parsed = AIInterpretationContent.model_validate(payload)
    assert parsed.key_findings == []
    assert parsed.business_implications == []
    assert parsed.recommendations == []


def test_insight_arrays_still_enforce_maximum_length():
    payload = {
        **VALID_INTERPRETATION,
        "business_implications": ["A valid implication."] * 11,
    }
    with pytest.raises(ValidationError):
        AIInterpretationContent.model_validate(payload)
