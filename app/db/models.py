"""SQLAlchemy ORM models for the geospatial measurement service."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FileModel(Base):
    """Represents an uploaded geospatial file and its processing status."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    # PENDING | PROCESSING | COMPLETED | FAILED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    crs: Mapped[str | None] = mapped_column(String(100), nullable=True)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    features: Mapped[list["FeatureModel"]] = relationship(
        "FeatureModel", back_populates="file", cascade="all, delete-orphan"
    )


class FeatureModel(Base):
    """Represents a single geographic feature extracted from a file."""

    __tablename__ = "features"
    __table_args__ = (Index("ix_features_file_id", "file_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # GeoJSON text
    geometry: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON serialised attribute dict
    properties: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # area | length | null
    measurement_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    measurement_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # m2 | m | null
    measurement_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # CRS code used for the projection (e.g. EPSG:32643)
    crs_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # OK | SKIPPED | UNSUPPORTED | ERROR
    measurement_status: Mapped[str] = mapped_column(String(20), nullable=False, default="OK")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped["FileModel"] = relationship("FileModel", back_populates="features")
