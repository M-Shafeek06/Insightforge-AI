from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.pdf_report import (
    generate_saved_analytics_pdf,
    pair_saved_interpretations,
    add_report_conclusion,
    build_styles,
)


def artifact(kind, title, source_id=None, payload=None):
    return SimpleNamespace(
        artifact_type=kind,
        title=title,
        source_execution_id=source_id,
        payload=payload or {},
        saved_at=datetime.now(timezone.utc),
    )


def test_saved_interpretations_pair_with_their_execution_in_saved_order():
    first = artifact("interpretation", "KPI AI Interpretation", "execution-1")
    second = artifact("interpretation", "Trend AI Interpretation", "execution-2")
    extra = artifact("interpretation", "Second KPI Interpretation", "execution-1")
    plan = artifact("deterministic_plan", "Business Plan")

    paired, unpaired = pair_saved_interpretations([first, plan, second, extra])

    assert [item.title for item in paired["execution-1"]] == [
        "KPI AI Interpretation",
        "Second KPI Interpretation",
    ]
    assert [item.title for item in paired["execution-2"]] == [
        "Trend AI Interpretation",
    ]
    assert unpaired == [plan]


def test_legacy_interpretation_payload_execution_id_is_supported():
    legacy = artifact(
        "interpretation",
        "Legacy Interpretation",
        payload={"execution_id": "execution-legacy"},
    )
    paired, unpaired = pair_saved_interpretations([legacy])
    assert paired["execution-legacy"] == [legacy]
    assert unpaired == []


def test_unlinked_interpretation_remains_a_separate_saved_item():
    orphan = artifact("interpretation", "Unlinked Interpretation")
    paired, unpaired = pair_saved_interpretations([orphan])
    assert paired == {}
    assert unpaired == [orphan]


def test_pdf_generation_returns_valid_pdf_and_preserves_saved_scope():
    now = datetime.now(timezone.utc)
    dataset = SimpleNamespace(filename="Retail & Sales.xlsx", id="dataset-1", created_at=now)
    execution = SimpleNamespace(
        execution_id="execution-1",
        operation="kpi",
        request_config={"column": "Sales", "aggregation": "sum"},
        result={"column": "Sales", "aggregation": "sum", "value": 1234.5},
        created_at=now,
        saved_at=now,
    )
    saved_interpretation = artifact(
        "interpretation",
        "AI Interpretation — KPI Analysis",
        "execution-1",
        {"executive_summary": "Review the saved KPI result."},
    )

    pdf = generate_saved_analytics_pdf(dataset, [execution], [saved_interpretation])
    data = pdf.getvalue()

    assert data.startswith(b"%PDF-")
    assert len(data) > 2_000



def test_report_conclusion_expands_saved_evidence_without_generating_new_content():
    now = datetime.now(timezone.utc)
    execution = SimpleNamespace(
        execution_id="execution-saved",
        operation="trend",
        request_config={"column": "Sales"},
        result={
            "column": "Sales",
            "interval": "month",
            "points": [
                {"period": "2026-01", "value": 100, "row_count": 10,
                 "valid_value_count": 10, "null_count": 0},
                {"period": "2026-02", "value": 150, "row_count": 12,
                 "valid_value_count": 12, "null_count": 0},
            ],
        },
        created_at=now,
        saved_at=now,
    )
    saved_interpretation = artifact(
        "interpretation",
        "Saved Trend Interpretation",
        "execution-saved",
        {
            "key_findings": [{
                "title": "Sales increased",
                "observation": "The final period is higher than the first period.",
                "business_impact": "The observed monthly value increased.",
            }],
            "recommendations": [{
                "priority": "medium",
                "action": "Review the next reporting period.",
                "rationale": "Confirm whether the observed change persists.",
            }],
        },
    )

    story = []
    add_report_conclusion(
        story,
        [execution],
        [saved_interpretation],
        build_styles(),
    )
    def collect_text(items):
        rendered = []
        for item in items:
            if hasattr(item, "getPlainText"):
                rendered.append(item.getPlainText())
            elif hasattr(item, "_content"):
                rendered.extend(collect_text(item._content))
        return rendered

    rendered_text = "\\n".join(collect_text(story))

    assert "Conclusion and Interpretation" in rendered_text
    assert "Analytical coverage" in rendered_text
    assert "First-to-last period comparison" in rendered_text
    assert "Saved AI findings" in rendered_text
    assert "Sales increased" in rendered_text
    assert "Saved recommendations" in rendered_text
    assert "Review the next reporting period." in rendered_text
    assert "No new calculations or AI interpretations" in rendered_text



def test_pdf_places_saved_business_planner_before_saved_analyses(monkeypatch):
    from app.services import pdf_report

    now = datetime.now(timezone.utc)
    dataset = SimpleNamespace(filename="Retail.xlsx", id="dataset-order", created_at=now)
    execution = SimpleNamespace(
        execution_id="execution-order",
        operation="kpi",
        request_config={"column": "Sales", "aggregation": "sum"},
        result={"column": "Sales", "aggregation": "sum", "value": 9876},
        created_at=now,
        saved_at=now,
    )
    planner = artifact(
        "deterministic_plan",
        "Saved Planner Strategy",
        payload={"business_objective": "PLANNER_SECTION_MARKER", "recommended_kpis": []},
    )
    captured = {}

    class CaptureDocument:
        def __init__(self, *args, **kwargs):
            pass

        def build(self, story, **kwargs):
            captured["story"] = story

    monkeypatch.setattr(pdf_report, "SimpleDocTemplate", CaptureDocument)
    pdf_report.generate_saved_analytics_pdf(dataset, [execution], [planner])

    headings = [
        item.getPlainText()
        for item in captured["story"]
        if hasattr(item, "getPlainText")
    ]
    assert headings.index("Business Planner") < headings.index("Analysis 1 of 1")
    assert "PLANNER_SECTION_MARKER" in headings


def test_conditional_page_break_does_not_create_blank_page_at_page_top():
    from app.services.pdf_report import PageBreakIfNotEmpty
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    flowable = PageBreakIfNotEmpty()
    frame_height = A4[1] - (22 * mm) - (19 * mm)
    assert flowable.wrap(500, frame_height) == (0, 0)
    width, height = flowable.wrap(500, frame_height - 100)
    assert width == 500
    assert height > frame_height - 101


def test_report_text_normalizes_nonbreaking_hyphens():
    from app.services.pdf_report import safe_text

    assert safe_text("mid‑year high‑value") == "mid-year high-value"
