from datetime import datetime
from uuid import UUID
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# ============================================================
# 1. DATASETS
# ============================================================

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_location: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ============================================================
# 2. DATASET VERSIONS
# ============================================================

class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    __table_args__ = (
        UniqueConstraint(
            "original_dataset_id",
            "version_number",
            name="uq_dataset_version_number",
        ),
        UniqueConstraint(
            "cleaning_plan_id",
            name="uq_dataset_version_cleaning_plan",
        ),
        CheckConstraint(
            "version_type IN ('original', 'cleaned')",
            name="ck_dataset_version_type",
        ),
        CheckConstraint(
            "version_number >= 0",
            name="ck_dataset_version_number",
        ),
    )

    dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        primary_key=True,
    )

    original_dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    version_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    cleaning_plan_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cleaning_plans.plan_id", ondelete="SET NULL"),
        nullable=True,
    )

    parent_dataset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


# ============================================================
# 3. CLEANING PLANS
# ============================================================

class CleaningPlan(Base):
    __tablename__ = "cleaning_plans"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'executed')",
            name="ck_cleaning_plan_status",
        ),
    )

    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )

    dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    source_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    operations: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
    )

    preview: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    cleaned_dataset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True,
    )

    execution_results: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    output_metrics: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    output_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# ============================================================
# 4. CLEANING EXECUTIONS
# ============================================================

class CleaningExecution(Base):
    __tablename__ = "cleaning_executions"

    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cleaning_plans.plan_id", ondelete="CASCADE"),
        primary_key=True,
    )

    dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )

    cleaned_dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )

    execution_results: Mapped[Any] = mapped_column(
        JSONB,
        nullable=False,
    )

    output_metrics: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    output_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


# ============================================================
# 5. ANALYTICS EXECUTIONS
# ============================================================

class AnalyticsExecution(Base):
    __tablename__ = "analytics_executions"

    __table_args__ = (
        CheckConstraint(
            """
            operation IN (
                'kpi',
                'descriptive',
                'trend',
                'segment_comparison',
                'correlation'
            )
            """,
            name="ck_analytics_execution_operation",
        ),
    )

    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )

    dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    operation: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    request_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    result: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Validated AI interpretation associated with this execution.
    # Nullable to preserve compatibility with existing executions.
    # Saving or unsaving an analysis does not modify this field.
    ai_interpretation: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


# ============================================================
# 6. SAVED ANALYTICS
# ============================================================

class SavedAnalytics(Base):
    __tablename__ = "saved_analytics"

    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "analytics_executions.execution_id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

# ============================================================
# 7. EXPLICITLY SAVED BUSINESS ARTEFACTS
# ============================================================

class SavedBusinessArtifact(Base):
    """Independently saved interpretations and planner outputs.

    The payload is a snapshot: later regeneration does not mutate it.
    A content hash makes repeated saves idempotent per dataset/type.
    """

    __tablename__ = "saved_business_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "artifact_type", "content_hash",
            name="uq_saved_business_artifact_content",
        ),
        CheckConstraint(
            "artifact_type IN ('interpretation', 'deterministic_plan', 'ai_business_plan')",
            name="ck_saved_business_artifact_type",
        ),
    )

    artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    dataset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("analytics_executions.execution_id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
