from datetime import datetime
import json
from io import BytesIO
from typing import Any

from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Drawing, String, Rect, Line, Circle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab import __file__ as reportlab_package_file
from pathlib import Path


class PageBreakIfNotEmpty(PageBreak):
    """Start a new page only when the current page already has content.

    ReportLab's stock PageBreakIfNotEmpty currently behaves exactly like
    PageBreak; this implementation avoids blank pages at page boundaries.
    """
    _frame_height = A4[1] - (22 * mm) - (19 * mm)

    def wrap(self, availWidth, availHeight):
        if availHeight >= self._frame_height - 1:
            self.width = 0
            self.height = 0
            return 0, 0
        return super().wrap(availWidth, availHeight)


# Vera is distributed with ReportLab and supports common Unicode punctuation
# that the built-in Helvetica fonts cannot render reliably.
_FONT_DIR = Path(reportlab_package_file).resolve().parent / "fonts"
_FONT_REGISTRATION_ERROR = None
try:
    pdfmetrics.registerFont(TTFont("IFVera", str(_FONT_DIR / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("IFVera-Bold", str(_FONT_DIR / "VeraBd.ttf")))
    pdfmetrics.registerFont(TTFont("IFVera-Italic", str(_FONT_DIR / "VeraIt.ttf")))
    pdfmetrics.registerFont(TTFont("IFVera-BoldItalic", str(_FONT_DIR / "VeraBI.ttf")))
    pdfmetrics.registerFontFamily(
        "IFVera", normal="IFVera", bold="IFVera-Bold",
        italic="IFVera-Italic", boldItalic="IFVera-BoldItalic",
    )
except Exception as exc:  # retain a safe built-in fallback if font registration fails
    _FONT_REGISTRATION_ERROR = exc
    IF_FONT = "Helvetica"
    IF_FONT_BOLD = "Helvetica-Bold"
else:
    IF_FONT = "IFVera"
    IF_FONT_BOLD = "IFVera-Bold"

# ============================================================
# REPORT THEME
# ============================================================

NAVY = colors.HexColor("#14213D")
CYAN = colors.HexColor("#0891B2")
LIGHT_CYAN = colors.HexColor("#E0F7FA")
LIGHT_GREY = colors.HexColor("#F1F5F9")
MID_GREY = colors.HexColor("#64748B")
DARK_GREY = colors.HexColor("#334155")
WHITE = colors.white
BORDER = colors.HexColor("#DCE5EF")


# ============================================================
# GENERAL HELPERS
# ============================================================

def format_number(value: Any) -> str:
    if value is None:
        return "Not available"

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, (int, float)):
        return f"{value:,.4f}".rstrip("0").rstrip(".")

    return str(value)


def format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d %B %Y, %I:%M %p")

    if value:
        return str(value)

    return "Not available"


def safe_text(value: Any) -> str:
    if value is None:
        return "Not available"

    # The bundled Vera font has broad Latin coverage but does not include
    # the Indian rupee glyph. Preserve the currency unambiguously as INR.
    text = str(value).replace("₹", "INR ")
    # Normalize punctuation not covered by the bundled Vera font.
    return (text.replace("\u2011", "-").replace("\u2010", "-")
            .replace("\u2012", "-").replace("\u2013", "-")
            .replace("\u2014", "-").replace("\u2212", "-")
            .replace("\u2022", "•").replace("\u00a0", " "))


def make_paragraph(
    text: Any,
    style: ParagraphStyle,
) -> Paragraph:
    """
    Escape arbitrary database values before inserting them
    into ReportLab Paragraph markup.
    """
    return Paragraph(
        escape(safe_text(text)),
        style,
    )


# ============================================================
# STYLES
# ============================================================

def build_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName=IF_FONT_BOLD,
            fontSize=27,
            leading=34,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=12,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=17,
            textColor=MID_GREY,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontName=IF_FONT_BOLD,
            fontSize=17,
            leading=22,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=9,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SubHeading",
            parent=styles["Heading2"],
            fontName=IF_FONT_BOLD,
            fontSize=11,
            leading=15,
            textColor=DARK_GREY,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="BodyTextCustom",
            parent=styles["BodyText"],
            fontSize=9,
            leading=14,
            textColor=DARK_GREY,
            spaceAfter=6,
    ))

    styles.add(
        ParagraphStyle(
            name="SmallText",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=MID_GREY,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ReportKicker",
            parent=styles["Normal"],
            fontName=IF_FONT_BOLD,
            fontSize=8,
            leading=11,
            textColor=CYAN,
            spaceBefore=4,
            spaceAfter=5,
            uppercase=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="Disclosure",
            parent=styles["Normal"],
            fontSize=8,
            leading=12,
            textColor=DARK_GREY,
            backColor=LIGHT_CYAN,
            borderColor=CYAN,
            borderWidth=0.6,
            borderPadding=9,
            spaceBefore=6,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="MetricValue",
            parent=styles["Normal"],
            fontName=IF_FONT_BOLD,
            fontSize=20,
            leading=25,
            textColor=NAVY,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=DARK_GREY,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableHeader",
            parent=styles["Normal"],
            fontName=IF_FONT_BOLD,
            fontSize=8,
            leading=11,
            textColor=WHITE,
        )
    )

    return styles


# ============================================================
# PAGE HEADER AND FOOTER
# ============================================================

def draw_page(canvas, document):
    canvas.saveState()

    width, height = A4

    if document.page > 1:
        canvas.setStrokeColor(BORDER)
        canvas.line(
            18 * mm,
            height - 14 * mm,
            width - 18 * mm,
            height - 14 * mm,
        )

        canvas.setFont(IF_FONT_BOLD, 8)
        canvas.setFillColor(NAVY)

        canvas.drawString(
            18 * mm,
            height - 11 * mm,
            "INSIGHTFORGE AI",
        )

        canvas.setFont(IF_FONT, 8)
        canvas.setFillColor(MID_GREY)

        canvas.drawRightString(
            width - 18 * mm,
            height - 11 * mm,
            "BUSINESS INTELLIGENCE REPORT",
        )

    canvas.setStrokeColor(BORDER)

    canvas.line(
        18 * mm,
        13 * mm,
        width - 18 * mm,
        13 * mm,
    )

    canvas.setFont(IF_FONT, 8)
    canvas.setFillColor(MID_GREY)

    canvas.drawString(
        18 * mm,
        8 * mm,
        "Generated by InsightForge AI  |  AI-assisted content — verify before acting",
    )

    canvas.drawRightString(
        width - 18 * mm,
        8 * mm,
        f"Page {document.page}",
    )

    canvas.restoreState()


# ============================================================
# TABLE HELPERS
# ============================================================

def create_table(
    data: list[list[Any]],
    widths=None,
):
    table = Table(
        data,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [WHITE, LIGHT_GREY],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    return table


def table_cell(value: Any, styles):
    return make_paragraph(
        value,
        styles["TableCell"],
    )


def table_header(value: Any, styles):
    return make_paragraph(
        value,
        styles["TableHeader"],
    )


# ============================================================
# ANALYSIS LABELS
# ============================================================

def operation_label(operation: str) -> str:
    labels = {
        "kpi": "KPI Analysis",
        "descriptive": "Descriptive Statistics",
        "trend": "Trend Analysis",
        "segment_comparison": "Segment Comparison",
        "correlation": "Correlation Analysis",
    }
    return labels.get(operation, operation.replace("_", " ").title())


def operation_title(
    operation: str,
    config: dict,
    result: dict,
) -> str:

    column = safe_text(
        result.get("column") or config.get("column")
    )

    if operation == "kpi":
        aggregation = safe_text(
            result.get("aggregation") or config.get("aggregation")
        ).upper()

        if "groups" in result:
            group_by = safe_text(
                result.get("group_by") or config.get("group_by")
            )

            return f"{aggregation} of {column} by {group_by}"

        return f"{aggregation} of {column}"

    if operation == "descriptive":
        return f"Descriptive Statistics — {column}"

    if operation == "trend":
        return f"Trend Analysis — {column}"

    if operation == "segment_comparison":
        segment = safe_text(
            result.get("segment_by") or config.get("group_by")
        )

        return f"Segment Comparison — {column} by {segment}"

    if operation == "correlation":
        second_column = safe_text(
            result.get("second_column") or config.get("second_column")
        )

        return f"Relationship — {column} and {second_column}"

    return operation_label(operation)


# ============================================================
# PDF CHART HELPERS
# ============================================================

CHART_WIDTH = 480
CHART_HEIGHT = 210

CHART_NAVY = NAVY
CHART_CYAN = CYAN


def add_chart_title(drawing, title):
    drawing.add(
        String(
            10,
            CHART_HEIGHT - 18,
            title,
            fontName=IF_FONT_BOLD,
            fontSize=10,
            fillColor=NAVY,
        )
    )


def add_bar_chart(story, labels, values, title, styles):
    """
    Render a simple bar chart from stored numeric results.
    """

    valid_items = [
        (str(label), float(value))
        for label, value in zip(labels, values)
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]

    if not valid_items:
        return

    labels, values = zip(*valid_items)

    drawing = Drawing(CHART_WIDTH, CHART_HEIGHT)
    add_chart_title(drawing, title)

    left = 55
    bottom = 45
    plot_width = 395
    plot_height = 125

    minimum = min(0, min(values))
    maximum = max(0, max(values))

    if minimum == maximum:
        maximum += 1

    padding = (maximum - minimum) * 0.12
    minimum -= padding
    maximum += padding

    def y_position(value):
        return bottom + (
            (value - minimum) / (maximum - minimum)
        ) * plot_height

    zero_y = y_position(0)

    drawing.add(
        Line(
            left,
            zero_y,
            left + plot_width,
            zero_y,
            strokeColor=MID_GREY,
            strokeWidth=0.8,
        )
    )

    slot_width = plot_width / len(values)
    bar_width = min(35, slot_width * 0.55)

    for index, (label, value) in enumerate(
        zip(labels, values)
    ):
        x = left + index * slot_width + (
            slot_width - bar_width
        ) / 2

        value_y = y_position(value)

        drawing.add(
            Rect(
                x,
                min(zero_y, value_y),
                bar_width,
                max(1, abs(value_y - zero_y)),
                fillColor=CYAN,
                strokeColor=CYAN,
            )
        )

        drawing.add(
            String(
                x + bar_width / 2,
                bottom - 13,
                label[:12],
                fontSize=7,
                textAnchor="middle",
                fillColor=DARK_GREY,
            )
        )

        drawing.add(
            String(
                x + bar_width / 2,
                max(zero_y, value_y) + 4,
                format_number(value)[:12],
                fontSize=7,
                textAnchor="middle",
                fillColor=NAVY,
            )
        )

    story.append(drawing)
    story.append(Spacer(1, 10))


def add_trend_chart(story, points):
    """
    Render stored trend values as a line chart.
    """

    valid_points = [
        point
        for point in points
        if isinstance(point.get("value"), (int, float))
        and not isinstance(point.get("value"), bool)
    ]

    if len(valid_points) < 2:
        return

    values = [float(point["value"]) for point in valid_points]

    minimum = min(values)
    maximum = max(values)

    if minimum == maximum:
        minimum -= 1
        maximum += 1

    drawing = Drawing(CHART_WIDTH, CHART_HEIGHT)

    add_chart_title(
        drawing,
        "Trend Visualization",
    )

    left = 55
    bottom = 48
    plot_width = 395
    plot_height = 120

    drawing.add(
        Line(
            left,
            bottom,
            left + plot_width,
            bottom,
            strokeColor=MID_GREY,
        )
    )

    drawing.add(
        Line(
            left,
            bottom,
            left,
            bottom + plot_height,
            strokeColor=MID_GREY,
        )
    )

    coordinates = []

    for index, value in enumerate(values):
        x = left + (
            index / (len(values) - 1)
        ) * plot_width

        y = bottom + (
            (value - minimum) / (maximum - minimum)
        ) * plot_height

        coordinates.append((x, y))

    for index in range(len(coordinates) - 1):
        x1, y1 = coordinates[index]
        x2, y2 = coordinates[index + 1]

        drawing.add(
            Line(
                x1,
                y1,
                x2,
                y2,
                strokeColor=CYAN,
                strokeWidth=2,
            )
        )

    for index, (x, y) in enumerate(coordinates):
        drawing.add(
            Circle(
                x,
                y,
                3,
                fillColor=CYAN,
                strokeColor=CYAN,
            )
        )

        if index in {
            0,
            len(coordinates) - 1,
        }:
            label = str(
                valid_points[index].get("period", "")
            )[:14]

            drawing.add(
                String(
                    x,
                    bottom - 15,
                    label,
                    fontSize=7,
                    textAnchor="middle",
                    fillColor=DARK_GREY,
                )
            )

    story.append(drawing)
    story.append(Spacer(1, 10))


def add_correlation_chart(story, points):
    """
    Render stored correlation coordinate pairs.
    """

    valid_points = []

    for point in points:
        x = point.get("x")
        y = point.get("y")

        if (
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and isinstance(y, (int, float))
            and not isinstance(y, bool)
        ):
            valid_points.append((float(x), float(y)))

    if not valid_points:
        return

    x_values = [point[0] for point in valid_points]
    y_values = [point[1] for point in valid_points]

    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)

    if x_min == x_max:
        x_min -= 1
        x_max += 1

    if y_min == y_max:
        y_min -= 1
        y_max += 1

    drawing = Drawing(CHART_WIDTH, CHART_HEIGHT)

    add_chart_title(
        drawing,
        "Correlation Scatter Plot",
    )

    left = 55
    bottom = 45
    plot_width = 395
    plot_height = 125

    drawing.add(
        Line(
            left,
            bottom,
            left + plot_width,
            bottom,
            strokeColor=MID_GREY,
        )
    )

    drawing.add(
        Line(
            left,
            bottom,
            left,
            bottom + plot_height,
            strokeColor=MID_GREY,
        )
    )

    for x_value, y_value in valid_points:
        x = left + (
            (x_value - x_min) / (x_max - x_min)
        ) * plot_width

        y = bottom + (
            (y_value - y_min) / (y_max - y_min)
        ) * plot_height

        drawing.add(
            Circle(
                x,
                y,
                2.5,
                fillColor=CYAN,
                strokeColor=CYAN,
            )
        )

    drawing.add(
        String(
            left + plot_width / 2,
            15,
            "X variable",
            fontSize=8,
            textAnchor="middle",
            fillColor=DARK_GREY,
        )
    )

    drawing.add(
        String(
            8,
            bottom + plot_height / 2,
            "Y",
            fontSize=8,
            fillColor=DARK_GREY,
        )
    )

    story.append(drawing)
    story.append(Spacer(1, 10))


# ============================================================
# ANALYSIS DETAILS
# ============================================================

def add_key_value_table(
    story,
    rows: list[tuple[str, Any]],
    styles,
):
    data = [
        [
            table_header("Metric", styles),
            table_header("Value", styles),
        ]
    ]

    for label, value in rows:
        data.append(
            [
                table_cell(label, styles),
                table_cell(format_number(value), styles),
            ]
        )

    story.append(
        create_table(
            data,
            widths=[65 * mm, 100 * mm],
        )
    )

    story.append(Spacer(1, 7))


def add_kpi_section(story, result, styles):
    story.append(
        make_paragraph(
            "KPI Results",
            styles["SubHeading"],
        )
    )

    if "groups" in result:
        groups = result.get("groups") or []

        data = [
            [
                table_header("Group", styles),
                table_header("Result", styles),
                table_header("Rows", styles),
                table_header("Valid", styles),
                table_header("Null", styles),
            ]
        ]

        for group in groups:
            data.append(
                [
                    table_cell(group.get("group"), styles),
                    table_cell(format_number(group.get("value")), styles),
                    table_cell(group.get("row_count"), styles),
                    table_cell(group.get("valid_value_count"), styles),
                    table_cell(group.get("null_count"), styles),
                ]
            )

        if len(data) == 1:
            story.append(
                make_paragraph(
                    "No groups were returned.",
                    styles["BodyTextCustom"],
                )
            )
        else:
            story.append(
                create_table(
                    data,
                    widths=[
                        43 * mm,
                        32 * mm,
                        27 * mm,
                        27 * mm,
                        27 * mm,
                    ],
                )
            )

            add_bar_chart(
                story,
                [group.get("group", "Unknown") for group in groups],
                [group.get("value") for group in groups],
                "Grouped KPI Comparison",
                styles,
            )

    else:
        add_key_value_table(
            story,
            [
                ("Calculated value", result.get("value")),
                ("Total rows", result.get("row_count")),
                ("Valid values", result.get("valid_value_count")),
                ("Null values", result.get("null_count")),
            ],
            styles,
        )


def add_descriptive_section(story, result, styles):
    statistics = result.get("statistics") or {}

    add_key_value_table(
        story,
        [
            ("Mean", statistics.get("mean")),
            ("Median", statistics.get("median")),
            ("Minimum", statistics.get("minimum")),
            ("Maximum", statistics.get("maximum")),
            ("Standard deviation", statistics.get("standard_deviation")),
            ("Total rows", result.get("row_count")),
            ("Valid values", result.get("valid_value_count")),
            ("Null values", result.get("null_count")),
        ],
        styles,
    )

    story.append(
        make_paragraph(
            "Standard deviation represents sample variability. "
            "A missing value indicates that the statistic was not "
            "available in the original calculation.",
            styles["SmallText"],
        )
    )

    story.append(
        make_paragraph(
            "The statistics are presented as individual values rather than a shared-scale chart. "
            "This avoids compressing the mean, median, and minimum when the maximum is much larger.",
            styles["SmallText"],
        )
    )

def add_trend_section(story, result, styles):
    points = result.get("points") or []

    data = [
        [
            table_header("Period", styles),
            table_header("Result", styles),
            table_header("Rows", styles),
            table_header("Valid", styles),
            table_header("Null", styles),
        ]
    ]

    for point in points:
        data.append(
            [
                table_cell(point.get("period"), styles),
                table_cell(format_number(point.get("value")), styles),
                table_cell(point.get("row_count"), styles),
                table_cell(point.get("valid_value_count"), styles),
                table_cell(point.get("null_count"), styles),
            ]
        )

    if len(data) == 1:
        story.append(
            make_paragraph(
                "No trend periods were returned.",
                styles["BodyTextCustom"],
            )
        )
    else:
        story.append(
            create_table(
                data,
                widths=[
                    43 * mm,
                    32 * mm,
                    27 * mm,
                    27 * mm,
                    27 * mm,
                ],
            )
        )

    story.append(Spacer(1, 6))

    story.append(
        make_paragraph(
            f"Time interval: {safe_text(result.get('interval'))}",
            styles["SmallText"],
        )
    )

    add_trend_chart(
        story,
        points,
    )

def add_segment_section(story, result, styles):
    segments = result.get("segments") or []

    data = [
        [
            table_header("Segment", styles),
            table_header("Result", styles),
            table_header("Rows", styles),
            table_header("Valid", styles),
            table_header("Null", styles),
        ]
    ]

    for segment in segments:
        data.append(
            [
                table_cell(segment.get("group"), styles),
                table_cell(format_number(segment.get("value")), styles),
                table_cell(segment.get("row_count"), styles),
                table_cell(segment.get("valid_value_count"), styles),
                table_cell(segment.get("null_count"), styles),
            ]
        )

    if len(data) == 1:
        story.append(
            make_paragraph(
                "No segments were returned.",
                styles["BodyTextCustom"],
            )
        )
    else:
        story.append(
            create_table(
                data,
                widths=[
                    43 * mm,
                    32 * mm,
                    27 * mm,
                    27 * mm,
                    27 * mm,
                ],
            )
        )

        add_bar_chart(
            story,
            [
                segment.get("group", "Unknown")
                for segment in segments
            ],
            [
                segment.get("value")
                for segment in segments
            ],
            "Segment Comparison",
            styles,
        )

def add_correlation_section(story, result, styles):
    add_key_value_table(
        story,
        [
            ("Pearson correlation", result.get("correlation")),
            ("Relationship strength", result.get("strength")),
            ("Direction", result.get("direction")),
            ("Paired observations", result.get("observation_count")),
            ("Sampled observations", result.get("sampled")),
        ],
        styles,
    )

    story.append(
        make_paragraph(
            "Pearson correlation measures linear association "
            "between two numeric variables. It does not establish "
            "causation. Only observations with valid values in both "
            "columns contribute to the calculation.",
            styles["SmallText"],
        )
    )

    add_correlation_chart(
        story,
        result.get("points") or [],
    )

# ============================================================
# DETERMINISTIC REPORT INSIGHTS
# ============================================================

def generate_report_insights(
    operation: str,
    result: dict,
) -> list[tuple[str, str]]:

    insights = []

    if operation == "kpi" and "groups" in result:
        groups = [
            group
            for group in result.get("groups", [])
            if isinstance(group.get("value"), (int, float))
            and not isinstance(group.get("value"), bool)
        ]

        if groups:
            highest = max(groups, key=lambda item: item["value"])
            lowest = min(groups, key=lambda item: item["value"])

            insights.append(
                (
                    "Highest calculated group",
                    f"{highest.get('group')} has the highest calculated "
                    f"value: {format_number(highest.get('value'))}.",
                )
            )

            insights.append(
                (
                    "Lowest calculated group",
                    f"{lowest.get('group')} has the lowest calculated "
                    f"value: {format_number(lowest.get('value'))}.",
                )
            )

            difference = highest["value"] - lowest["value"]

            insights.append(
                (
                    "Difference between extremes",
                    "The absolute difference between the highest and "
                    f"lowest calculated groups is {format_number(difference)}.",
                )
            )

    elif operation == "descriptive":
        statistics = result.get("statistics") or {}

        mean = statistics.get("mean")
        median = statistics.get("median")

        if isinstance(mean, (int, float)) and isinstance(median, (int, float)):
            if mean > median:
                description = "The mean is greater than the median."
            elif mean < median:
                description = "The mean is lower than the median."
            else:
                description = "The mean and median are equal."

            insights.append(
                ("Central tendency comparison", description)
            )

    elif operation == "trend":
        points = [
            point
            for point in result.get("points", [])
            if isinstance(point.get("value"), (int, float))
            and not isinstance(point.get("value"), bool)
        ]

        if len(points) >= 2:
            first = points[0]
            last = points[-1]

            if last["value"] > first["value"]:
                direction = "higher"
            elif last["value"] < first["value"]:
                direction = "lower"
            else:
                direction = "unchanged"

            insights.append(
                (
                    "First-to-last period comparison",
                    f"The last valid period value is {direction} than "
                    "the first valid period value.",
                )
            )

    elif operation == "segment_comparison":
        segments = [
            segment
            for segment in result.get("segments", [])
            if isinstance(segment.get("value"), (int, float))
            and not isinstance(segment.get("value"), bool)
        ]

        if segments:
            highest = max(segments, key=lambda item: item["value"])
            lowest = min(segments, key=lambda item: item["value"])

            insights.append(
                (
                    "Highest segment",
                    f"{highest.get('group')} has the highest calculated "
                    f"value: {format_number(highest.get('value'))}.",
                )
            )

            insights.append(
                (
                    "Lowest segment",
                    f"{lowest.get('group')} has the lowest calculated "
                    f"value: {format_number(lowest.get('value'))}.",
                )
            )

    elif operation == "correlation":
        correlation = result.get("correlation")

        if isinstance(correlation, (int, float)):
            insights.append(
                (
                    "Linear relationship",
                    f"The Pearson correlation coefficient is "
                    f"{format_number(correlation)}. The calculated "
                    f"strength is {safe_text(result.get('strength'))}, "
                    f"with {safe_text(result.get('direction'))} direction.",
                )
            )

    return insights


# ============================================================
# AI BUSINESS INTERPRETATION
# ============================================================

def add_ai_interpretation_section(
    story,
    interpretation,
    styles,
    heading="AI Business Interpretation",
):
    """
    Render persisted AI interpretation for a saved execution.

    This function does not generate AI content, save analytics,
    or modify database records.
    """

    if not isinstance(interpretation, dict) or not interpretation:
        return

    story.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=CYAN,
            spaceBefore=10,
            spaceAfter=10,
        )
    )

    story.append(
        make_paragraph(
            heading,
            styles["SectionHeading"],
        )
    )

    provider = interpretation.get("provider", "Not specified")
    model = interpretation.get("model", "Not specified")

    story.append(
        make_paragraph(
            f"AI Provider: {provider} | Model: {model}",
            styles["SmallText"],
        )
    )

    # Executive Summary
    executive_summary = interpretation.get("executive_summary")

    if executive_summary:
        story.append(
            make_paragraph(
                "Executive Summary",
                styles["SubHeading"],
            )
        )

        story.append(
            make_paragraph(
                executive_summary,
                styles["BodyTextCustom"],
            )
        )

    # Key Findings
    findings = interpretation.get("key_findings") or []

    if findings:
        story.append(
            make_paragraph(
                "Key Findings",
                styles["SubHeading"],
            )
        )

        for index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                continue

            story.append(
                KeepTogether(
                    [
                        make_paragraph(
                            f"{index}. {finding.get('title', 'Finding')}",
                            styles["SubHeading"],
                        ),
                        make_paragraph(
                            f"Observation: {finding.get('observation', '')}",
                            styles["BodyTextCustom"],
                        ),
                        make_paragraph(
                            f"Business Impact: "
                            f"{finding.get('business_impact', '')}",
                            styles["BodyTextCustom"],
                        ),
                    ]
                )
            )

    # Business Implications
    implications = interpretation.get("business_implications") or []

    if implications:
        story.append(
            make_paragraph(
                "Business Implications",
                styles["SubHeading"],
            )
        )

        for implication in implications:
            story.append(
                make_paragraph(
                    f"• {implication}",
                    styles["BodyTextCustom"],
                )
            )

    # Risks and Limitations
    risks = interpretation.get("risks_and_limitations") or []

    if risks:
        story.append(
            make_paragraph(
                "Risks & Limitations",
                styles["SubHeading"],
            )
        )

        for risk in risks:
            story.append(
                make_paragraph(
                    f"• {risk}",
                    styles["BodyTextCustom"],
                )
            )

    # Recommendations
    recommendations = interpretation.get("recommendations") or []

    if recommendations:
        story.append(
            make_paragraph(
                "Actionable Recommendations",
                styles["SubHeading"],
            )
        )

        recommendation_data = [
            [
                table_header("Priority", styles),
                table_header("Recommended Action", styles),
                table_header("Rationale", styles),
            ]
        ]

        for recommendation in recommendations:
            if not isinstance(recommendation, dict):
                continue

            priority = safe_text(
                recommendation.get("priority", "medium")
            ).upper()

            recommendation_data.append(
                [
                    table_cell(priority, styles),
                    table_cell(
                        recommendation.get("action"),
                        styles,
                    ),
                    table_cell(
                        recommendation.get("rationale"),
                        styles,
                    ),
                ]
            )

        if len(recommendation_data) > 1:
            story.append(
                create_table(
                    recommendation_data,
                    widths=[
                        25 * mm,
                        65 * mm,
                        80 * mm,
                    ],
                )
            )

    story.append(Spacer(1, 12))


# ============================================================
# INDIVIDUAL ANALYSIS REPORT
# ============================================================

def add_analysis_report(
    story,
    execution,
    styles,
    interpretation=None,
    interpretation_heading="AI Business Interpretation",
):
    operation = execution.operation
    config = execution.request_config or {}
    result = execution.result or {}

    story.append(
        make_paragraph(
            operation_title(operation, config, result),
            styles["SectionHeading"],
        )
    )

    metadata = [
        ("Analysis type", operation_label(operation)),
        ("Execution ID", execution.execution_id),
        ("Executed at", format_datetime(execution.created_at)),
        ("Saved at", format_datetime(execution.saved_at)),
        ("Analyzed column", result.get("column")),
    ]

    if operation == "kpi":
        metadata.append(
            ("Aggregation", result.get("aggregation"))
        )

        if "groups" in result:
            metadata.append(
                ("Grouping column", result.get("group_by"))
            )

    elif operation == "trend":
        metadata.extend(
            [
                ("Date column", result.get("date_column")),
                ("Time interval", result.get("interval")),
            ]
        )

    elif operation == "segment_comparison":
        metadata.append(
            ("Segment column", result.get("segment_by"))
        )

    elif operation == "correlation":
        metadata.append(
            ("Second column", result.get("second_column"))
        )

    add_key_value_table(
        story,
        metadata,
        styles,
    )

    # Analytical results
    if operation == "kpi":
        add_kpi_section(story, result, styles)

    elif operation == "descriptive":
        add_descriptive_section(story, result, styles)

    elif operation == "trend":
        add_trend_section(story, result, styles)

    elif operation == "segment_comparison":
        add_segment_section(story, result, styles)

    elif operation == "correlation":
        add_correlation_section(story, result, styles)

    else:
        story.append(
            make_paragraph(
                "This saved execution has an unsupported operation "
                "format. Its stored result is preserved but could "
                "not be rendered as a standard analysis section.",
                styles["BodyTextCustom"],
            )
        )

    # Deterministic observations
    insights = generate_report_insights(
        operation,
        result,
    )

    story.append(
        make_paragraph(
            "Deterministic observations",
            styles["SubHeading"],
        )
    )

    if not insights:
        story.append(
            make_paragraph(
                "The stored result does not contain sufficient "
                "information for an additional deterministic "
                "observation.",
                styles["BodyTextCustom"],
            )
        )
    else:
        for title, description in insights:
            story.append(
                KeepTogether(
                    [
                        make_paragraph(
                            title,
                            styles["SubHeading"],
                        ),
                        make_paragraph(
                            description,
                            styles["BodyTextCustom"],
                        ),
                    ]
                )
            )

    # Include an AI interpretation only when that interpretation itself
    # was explicitly saved and linked to this execution.
    if isinstance(interpretation, dict) and interpretation:
        add_ai_interpretation_section(
            story,
            interpretation,
            styles,
            heading=interpretation_heading,
        )

    # Avoid a trailing rule being pushed onto an otherwise empty page by
    # ReportLab when a long analysis ends near the frame boundary.
    story.append(Spacer(1, 5))


# ============================================================
# BUSINESS PLAN RENDERING (STRUCTURED, HUMAN-READABLE)
# ============================================================

def _display_label(value: Any) -> str:
    return str(value).replace("_", " ").replace("-", " ").strip().title()


def _render_bullet_list(story, values, styles, limit=100):
    for item in values[:limit]:
        if isinstance(item, dict):
            title = item.get("name") or item.get("title") or item.get("question")
            description = item.get("description") or item.get("business_value") or item.get("rationale")
            if title and description:
                story.append(Paragraph(f"<b>{escape(str(title))}</b><br/>{escape(str(description))}", styles["BodyTextCustom"]))
            elif title:
                story.append(make_paragraph(title, styles["BodyTextCustom"]))
            else:
                for key, value in item.items():
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        story.append(make_paragraph(f"{_display_label(key)}: {safe_text(value)}", styles["BodyTextCustom"]))
        elif isinstance(item, (str, int, float, bool)) or item is None:
            story.append(make_paragraph(item, styles["BodyTextCustom"]))


def _render_recommendation_table(story, rows, headers, styles, widths=None):
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        story.append(make_paragraph("No items were provided.", styles["BodyTextCustom"]))
        return
    data = [[table_header(_display_label(h), styles) for h in headers]]
    for row in rows:
        data.append([table_cell(row.get(h), styles) for h in headers])
    story.append(create_table(data, widths=widths))
    story.append(Spacer(1, 7))


def add_business_plan_section(story, payload, styles, artifact_type):
    """Render saved deterministic/AI planner snapshots without raw JSON dumps."""
    plan = payload.get("analysis_plan") if isinstance(payload.get("analysis_plan"), dict) else payload
    if not isinstance(plan, dict):
        story.append(make_paragraph("The saved plan does not contain a readable structured payload.", styles["BodyTextCustom"]))
        return

    # Planner responses may wrap the actual plan under a result/data key.
    for wrapper in ("result", "data", "plan"):
        if isinstance(plan.get(wrapper), dict) and len(plan) <= 4:
            plan = plan[wrapper]
            break

    preferred = [
        ("business_objective", "Business Objective"),
        ("refined_objective", "Refined Objective"),
        ("reasoning_summary", "Analysis Rationale"),
        ("feasibility_reason", "Feasibility Assessment"),
    ]
    for key, heading in preferred:
        value = plan.get(key)
        if value not in (None, ""):
            story.append(make_paragraph(heading, styles["SubHeading"]))
            story.append(make_paragraph(value, styles["BodyTextCustom"]))

    feasibility = plan.get("feasibility_status")
    if feasibility:
        story.append(make_paragraph(f"Plan status: {_display_label(feasibility)}", styles["ReportKicker"]))

    sections = [
        (("recommended_kpis", "recommended_kpis"), "Recommended KPIs"),
        (("recommended_analyses",), "Recommended Analyses"),
        (("business_questions",), "Business Questions"),
        (("clarifying_questions",), "Clarifying Questions"),
        (("recommended_focus_areas", "focus_areas"), "Recommended Focus Areas"),
    ]
    for keys, heading in sections:
        value = next((plan.get(key) for key in keys if isinstance(plan.get(key), list)), None)
        if value:
            story.append(make_paragraph(heading, styles["SubHeading"]))
            if heading == "Recommended KPIs":
                _render_recommendation_table(story, value, ["name", "calculation", "description"], styles, [35*mm, 38*mm, 77*mm])
            elif heading == "Recommended Analyses":
                _render_recommendation_table(story, value, ["name", "description", "business_value", "analysis_method"], styles, [30*mm, 48*mm, 48*mm, 24*mm])
            else:
                _render_bullet_list(story, value, styles)

    warnings = plan.get("quality_warnings")
    if isinstance(warnings, list) and warnings:
        story.append(make_paragraph("Data Quality Considerations", styles["SubHeading"]))
        warning_rows = []
        for warning in warnings:
            if isinstance(warning, dict):
                warning_rows.append({
                    "severity": str(warning.get("severity", "info")).upper(),
                    "column": warning.get("column", "Dataset"),
                    "issue": warning.get("message") or warning.get("issue_type"),
                    "action": warning.get("recommendation", "Review the source data."),
                })
        _render_recommendation_table(story, warning_rows, ["severity", "column", "issue", "action"], styles, [19*mm, 27*mm, 58*mm, 56*mm])

    missing = plan.get("missing_required_columns") or plan.get("missing_columns")
    if missing:
        story.append(make_paragraph("Missing Required Columns", styles["SubHeading"]))
        _render_bullet_list(story, missing if isinstance(missing, list) else [missing], styles)

    # Render remaining structured scalar metadata, but never dump nested JSON.
    known = {key for keys, _ in sections for key in keys}
    known.update(key for key, _ in preferred)
    known.update({"feasibility_status", "quality_warnings", "missing_required_columns", "missing_columns", "available_columns", "dataset_id", "ai_assisted"})
    remaining = [(key, value) for key, value in plan.items() if key not in known and isinstance(value, (str, int, float, bool)) and value not in (None, "")]
    if remaining:
        story.append(make_paragraph("Additional Plan Details", styles["SubHeading"]))
        add_key_value_table(story, [(_display_label(k), v) for k, v in remaining], styles)

    available_columns = plan.get("available_columns")
    if isinstance(available_columns, list) and available_columns:
        story.append(make_paragraph("Available Dataset Columns", styles["SubHeading"]))
        _render_bullet_list(story, [", ".join(map(str, available_columns))], styles)

    if artifact_type == "ai_business_plan" or plan.get("ai_assisted"):
        story.append(make_paragraph(
            "AI-assisted plan: recommendations are generated from the supplied objective and detected dataset structure. Confirm column suitability, business definitions, and feasibility before execution.",
            styles["Disclosure"],
        ))


# ============================================================
# SAVED ARTIFACT ASSOCIATION
# ============================================================

def pair_saved_interpretations(saved_artifacts):
    """Return explicitly saved interpretations grouped by source execution.

    Legacy interpretation payloads may carry execution_id even when the
    nullable source_execution_id foreign key was not populated.
    """
    paired = {}
    unpaired = []
    for artifact in saved_artifacts or []:
        if getattr(artifact, "artifact_type", None) != "interpretation":
            unpaired.append(artifact)
            continue
        payload = artifact.payload if isinstance(artifact.payload, dict) else {}
        source_id = getattr(artifact, "source_execution_id", None) or payload.get("execution_id")
        key = str(source_id) if source_id is not None else None
        if key:
            paired.setdefault(key, []).append(artifact)
        else:
            unpaired.append(artifact)
    return paired, unpaired


def add_report_conclusion(story, saved_analyses, saved_artifacts, styles):
    """Build an evidence-led conclusion from explicitly saved snapshots only."""
    story.append(make_paragraph("Conclusion and Interpretation", styles["SectionHeading"]))

    if not saved_analyses and not saved_artifacts:
        story.append(make_paragraph(
            "No saved analytical evidence is available for a conclusion.",
            styles["BodyTextCustom"],
        ))
        return

    operation_counts = {}
    for execution in saved_analyses:
        label = operation_label(getattr(execution, "operation", "unknown"))
        operation_counts[label] = operation_counts.get(label, 0) + 1

    story.append(make_paragraph(
        f"This report is based on {len(saved_analyses)} explicitly saved "
        f"analytical execution(s) and {len(saved_artifacts)} separately saved "
        "business item(s). The conclusion below is restricted to those saved "
        "snapshots; analyses that were executed but not saved are excluded.",
        styles["BodyTextCustom"],
    ))

    if operation_counts:
        coverage = "; ".join(
            f"{label}: {count}" for label, count in sorted(operation_counts.items())
        )
        story.append(make_paragraph(
            f"Analytical coverage: {coverage}.",
            styles["BodyTextCustom"],
        ))

    # Consolidate deterministic observations from each saved execution.
    observation_rows = []
    for execution in saved_analyses:
        result = getattr(execution, "result", None) or {}
        operation = getattr(execution, "operation", "unknown")
        title = operation_title(
            operation,
            getattr(execution, "request_config", None) or {},
            result,
        )
        for insight_title, insight_text in generate_report_insights(operation, result):
            observation_rows.append((title, insight_title, insight_text))

    if observation_rows:
        story.append(make_paragraph(
            "Evidence-based observations across saved analyses",
            styles["SubHeading"],
        ))
        for analysis_title, insight_title, insight_text in observation_rows[:18]:
            story.append(KeepTogether([
                make_paragraph(
                    f"{analysis_title} — {insight_title}",
                    styles["SubHeading"],
                ),
                make_paragraph(insight_text, styles["BodyTextCustom"]),
            ]))

    # Bring forward saved AI findings and actions without generating new AI
    # content or treating unsaved interpretations as report evidence.
    saved_findings = []
    saved_recommendations = []
    for artifact in saved_artifacts:
        payload = getattr(artifact, "payload", None)
        if not isinstance(payload, dict):
            continue
        findings = payload.get("key_findings")
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    title = finding.get("title")
                    observation = finding.get("observation")
                    impact = finding.get("business_impact")
                    if title or observation:
                        saved_findings.append((title, observation, impact))
        recommendations = payload.get("recommendations")
        if isinstance(recommendations, list):
            for recommendation in recommendations:
                if isinstance(recommendation, dict):
                    action = recommendation.get("action")
                    rationale = recommendation.get("rationale")
                    priority = recommendation.get("priority")
                    if action:
                        saved_recommendations.append((priority, action, rationale))

    if saved_findings:
        story.append(make_paragraph(
            "Saved AI findings",
            styles["SubHeading"],
        ))
        for title, observation, impact in saved_findings[:15]:
            parts = []
            if title:
                parts.append(str(title))
            if observation:
                parts.append(f"Observation: {observation}")
            if impact:
                parts.append(f"Business impact: {impact}")
            story.append(make_paragraph(" • ".join(parts), styles["BodyTextCustom"]))

    if saved_recommendations:
        story.append(make_paragraph(
            "Saved recommendations",
            styles["SubHeading"],
        ))
        # Render each saved recommendation as normal Paragraph flowables rather
        # than hiding the text inside a Table. This keeps the complete action
        # and rationale readable, searchable, and accessible to downstream
        # PDF-content checks while allowing ReportLab to split long content
        # naturally across pages.
        for index, (priority, action, rationale) in enumerate(
            saved_recommendations[:15], start=1
        ):
            story.append(make_paragraph(
                f"Recommendation {index} — Priority: {priority or 'Not specified'}",
                styles["ReportKicker"],
            ))
            story.append(make_paragraph(
                action,
                styles["BodyTextCustom"],
            ))
            if rationale:
                story.append(make_paragraph(
                    f"Rationale: {rationale}",
                    styles["BodyTextCustom"],
                ))
            else:
                story.append(make_paragraph(
                    "Rationale: No rationale supplied.",
                    styles["BodyTextCustom"],
                ))

    story.append(make_paragraph(
        "Interpretation boundaries",
        styles["SubHeading"],
    ))
    story.append(make_paragraph(
        "These results describe the selected columns, filters, aggregation "
        "methods, date intervals, and records represented in each saved "
        "execution. A higher or lower calculated value is not, by itself, "
        "proof of business success or failure. Correlation does not establish "
        "causation, and descriptive or grouped results do not establish "
        "statistical significance unless that evidence was explicitly "
        "calculated and saved.",
        styles["BodyTextCustom"],
    ))
    story.append(make_paragraph(
        "Recommendations reproduced above are those contained in saved "
        "interpretations. Validate them against business definitions, data "
        "coverage, operational constraints, and additional evidence before "
        "taking action. No new calculations or AI interpretations are "
        "generated during PDF creation.",
        styles["BodyTextCustom"],
    ))


# ============================================================
# COMPLETE PDF GENERATION
# ============================================================

def generate_saved_analytics_pdf(
    dataset,
    saved_analyses: list,
    saved_artifacts: list | None = None,
) -> BytesIO:
    """
    Generate a downloadable PDF using explicitly saved
    analytics executions only.

    The function performs no database writes and does not
    rerun analytical calculations.
    """

    saved_artifacts = saved_artifacts or []
    if not saved_analyses and not saved_artifacts:
        raise ValueError("No saved business artefacts are available for this report.")

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=19 * mm,
        title=f"InsightForge AI Report - {dataset.filename}",
        author="InsightForge AI",
        subject="Saved Business Analytics Report",
    )

    styles = build_styles()
    story = []

    generated_at = datetime.now().astimezone()

    # --------------------------------------------------------
    # COVER PAGE
    # --------------------------------------------------------

    story.append(Spacer(1, 36 * mm))

    story.append(
        make_paragraph(
            "INSIGHTFORGE AI",
            ParagraphStyle(
                name="Brand",
                fontName=IF_FONT_BOLD,
                fontSize=13,
                textColor=CYAN,
                leading=18,
            ),
        )
    )

    story.append(Spacer(1, 10 * mm))

    story.append(
        Paragraph(
            "Business Analytics<br/>&amp; Decision Intelligence Report",
            styles["ReportTitle"],
        )
    )

    story.append(
        make_paragraph(
            "A consolidated report of explicitly saved "
            "analytical results.",
            styles["ReportSubtitle"],
        )
    )

    story.append(Spacer(1, 12 * mm))

    story.append(
        HRFlowable(
            width="100%",
            thickness=2,
            color=CYAN,
            spaceAfter=12,
        )
    )

    cover_rows = [
        ("Dataset", dataset.filename),
        ("Dataset ID", dataset.id),
        ("Uploaded at", format_datetime(dataset.created_at)),
        ("Report generated", format_datetime(generated_at)),
        ("Saved executions included", len(saved_analyses)),
        ("Separately saved business items", len(saved_artifacts)),
    ]

    add_key_value_table(
        story,
        cover_rows,
        styles,
    )

    story.append(Spacer(1, 18 * mm))

    story.append(
        make_paragraph(
            "Report scope",
            styles["SubHeading"],
        )
    )

    story.append(
        make_paragraph(
            "This report includes only executions, interpretations, and planner outputs explicitly saved by the user. Unsaved generated content and unsaved execution history are excluded. Stored snapshots are used; calculations and AI generation are not rerun during report generation.",
            styles["BodyTextCustom"],
        )
    )

    story.append(make_paragraph(
        "AI CONTENT NOTICE  |  AI-generated interpretations and recommendations may contain errors, omissions, or unsupported assumptions. Verify statements against the underlying data and relevant business context before relying on them. AI output is decision support, not a substitute for professional judgement.",
        styles["Disclosure"],
    ))

    story.append(PageBreak())

    # --------------------------------------------------------
    # EXECUTIVE SUMMARY
    # --------------------------------------------------------

    story.append(
        make_paragraph(
            "Executive Summary",
            styles["SectionHeading"],
        )
    )

    story.append(
        make_paragraph(
            f"This report contains {len(saved_analyses)} saved analytical execution(s) and {len(saved_artifacts)} separately saved business item(s). Each item appears only when its Save action was used.",
            styles["BodyTextCustom"],
        )
    )

    summary_data = [
        [
            table_header("Analysis", styles),
            table_header("Operation", styles),
            table_header("Saved at", styles),
        ]
    ]

    # Business Planner content precedes executed analyses to match the
    # product workflow: plan first, then execute and review the analysis.
    planner_artifacts = [
        artifact for artifact in saved_artifacts
        if getattr(artifact, "artifact_type", None) in {"deterministic_plan", "ai_business_plan"}
    ]
    interpretation_artifacts = [
        artifact for artifact in saved_artifacts
        if getattr(artifact, "artifact_type", None) == "interpretation"
    ]

    for artifact in planner_artifacts:
        summary_data.append([
            table_cell(artifact.title, styles),
            table_cell(artifact.artifact_type.replace("_", " ").title(), styles),
            table_cell(format_datetime(artifact.saved_at), styles),
        ])

    for execution in saved_analyses:
        summary_data.append(
            [
                table_cell(
                    operation_title(
                        execution.operation,
                        execution.request_config or {},
                        execution.result or {},
                    ),
                    styles,
                ),
                table_cell(
                    operation_label(execution.operation),
                    styles,
                ),
                table_cell(
                    format_datetime(execution.saved_at),
                    styles,
                ),
            ]
        )

    for artifact in interpretation_artifacts:
        summary_data.append([
            table_cell(artifact.title, styles),
            table_cell("Saved Interpretation", styles),
            table_cell(format_datetime(artifact.saved_at), styles),
        ])

    story.append(
        create_table(
            summary_data,
            widths=[
                68 * mm,
                38 * mm,
                50 * mm,
            ],
        )
    )

    story.append(Spacer(1, 12))
    story.append(PageBreakIfNotEmpty())

    # --------------------------------------------------------
    # INDIVIDUAL SAVED ANALYSES + THEIR SAVED AI INTERPRETATIONS
    # --------------------------------------------------------
    # Pair by the explicit foreign-key association. A payload execution_id
    # fallback supports older saved artifact rows created before the FK was
    # populated. No unsaved interpretation is ever included.
    def _execution_key(value):
        return str(value) if value is not None else None

    paired_interpretations, unpaired_artifacts = pair_saved_interpretations(saved_artifacts)
    planner_artifacts = [
        artifact for artifact in unpaired_artifacts
        if getattr(artifact, "artifact_type", None) in {"deterministic_plan", "ai_business_plan"}
    ]
    # --------------------------------------------------------
    # BUSINESS PLANNER — intentionally before executed analyses
    # --------------------------------------------------------
    if planner_artifacts:
        story.append(make_paragraph("Business Planner", styles["SectionHeading"]))
        story.append(make_paragraph(
            "The following business plans were explicitly saved from the Business Planner.",
            styles["BodyTextCustom"],
        ))
        for artifact_index, artifact in enumerate(planner_artifacts):
            if artifact_index > 0:
                story.append(PageBreakIfNotEmpty())
            story.append(make_paragraph(artifact.title, styles["SubHeading"]))
            payload = artifact.payload if isinstance(artifact.payload, dict) else {}
            add_business_plan_section(story, payload, styles, artifact.artifact_type)

    # --------------------------------------------------------
    # ANALYSIS + ITS EXPLICITLY SAVED INTERPRETATIONS
    # --------------------------------------------------------
    for index, execution in enumerate(saved_analyses, start=1):
        if index > 1:
            story.append(PageBreakIfNotEmpty())
        story.append(
            make_paragraph(
                f"Analysis {index} of {len(saved_analyses)}",
                styles["ReportKicker"],
            )
        )
        execution_key = _execution_key(getattr(execution, "execution_id", None))
        linked = paired_interpretations.pop(execution_key, []) if execution_key else []
        # Normally one interpretation is saved per execution. If a user has
        # explicitly saved more than one, preserve all of them in save order.
        interpretation_payload = None
        if linked:
            first_payload = linked[0].payload if isinstance(linked[0].payload, dict) else {}
            interpretation_payload = first_payload
        add_analysis_report(
            story,
            execution,
            styles,
            interpretation=interpretation_payload,
            interpretation_heading=(safe_text(getattr(linked[0], "title", "AI Business Interpretation")) if linked else "AI Business Interpretation"),
        )
        for extra_artifact in linked[1:]:
            extra_payload = extra_artifact.payload if isinstance(extra_artifact.payload, dict) else {}
            add_ai_interpretation_section(
                story,
                extra_payload,
                styles,
                heading="Additional Saved AI Interpretation",
            )

    # Orphaned interpretation records (legacy records without an execution
    # association) remain visible as separately saved items rather than being
    # silently discarded or incorrectly attached to an analysis.
    for items in paired_interpretations.values():
        unpaired_artifacts.extend(items)

    standalone_interpretations = [
        artifact for artifact in unpaired_artifacts
        if getattr(artifact, "artifact_type", None) == "interpretation"
    ]

    # --------------------------------------------------------
    # STANDALONE SAVED INTERPRETATIONS (not linked to an analysis)
    # --------------------------------------------------------
    if standalone_interpretations:
        story.append(PageBreakIfNotEmpty())
        story.append(make_paragraph("Standalone Saved Interpretations", styles["SectionHeading"]))
        story.append(make_paragraph(
            "These explicitly saved interpretations were not associated with a specific analysis execution.",
            styles["BodyTextCustom"],
        ))
        for artifact_index, artifact in enumerate(standalone_interpretations):
            if artifact_index > 0:
                story.append(PageBreakIfNotEmpty())
            story.append(make_paragraph(artifact.title, styles["SubHeading"]))
            payload = artifact.payload if isinstance(artifact.payload, dict) else {}
            add_ai_interpretation_section(story, payload, styles)

    # --------------------------------------------------------
    # CONCLUSION
    # --------------------------------------------------------

    story.append(PageBreakIfNotEmpty())
    add_report_conclusion(
        story,
        saved_analyses,
        saved_artifacts,
        styles,
    )

    document.build(
        story,
        onFirstPage=draw_page,
        onLaterPages=draw_page,
    )

    buffer.seek(0)

    return buffer
