import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# SQLAlchemy ORM Base & Models
# ----------------------------------------------------------------------

class Base(DeclarativeBase):
    """Base declarative class for all database models."""
    pass


class RawPayloadModel(Base):
    """Tracks raw ingested source data with version control and SHA-256 hash tracking."""

    __tablename__ = "raw_payloads"

    payload_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text/plain")
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Composite primary key allowing version history for the same payload_id
    __table_args__ = (
        PrimaryKeyConstraint("payload_id", "version", name="pk_raw_payloads_id_version"),
    )

    # Relationships
    parsed_documents: Mapped[List["DocumentModel"]] = relationship(
        "DocumentModel", back_populates="raw_payload", cascade="all, delete-orphan"
    )


class DocumentModel(Base):
    """Represents normalized and parsed content generated from a specific RawPayload version."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payload_id: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Foreign key constraint to RawPayload composite key
    raw_payload: Mapped["RawPayloadModel"] = relationship(
        "RawPayloadModel",
        back_populates="parsed_documents",
        primaryjoin="and_(DocumentModel.payload_id==RawPayloadModel.payload_id, "
                    "DocumentModel.payload_version==RawPayloadModel.version)",
    )
    
    chunks: Mapped[List["TextChunkModel"]] = relationship(
        "TextChunkModel", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["payload_id", "payload_version"],
            ["raw_payloads.payload_id", "raw_payloads.version"],
            name="fk_documents_raw_payload",
        ),
    )


class TextChunkModel(Base):
    """Represents split text chunks linked to active document versions."""

    __tablename__ = "text_chunks"

    chunk_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_purged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="chunks")


# ----------------------------------------------------------------------
# Database Manager
# ----------------------------------------------------------------------

class DatabaseManager:
    """Manages database connection sessions, version upserts, and payload lifecycle status."""

    def __init__(self, database_url: str = settings.DATABASE_URL):
        self.engine = create_engine(database_url, echo=False, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self) -> None:
        """Initializes tables directly (useful for local development/testing without Alembic)."""
        Base.metadata.create_all(bind=self.engine)

    @staticmethod
    def compute_hash(raw_data: Union[str, bytes]) -> str:
        """Generates SHA-256 signature for payload deduplication and change detection."""
        if isinstance(raw_data, str):
            raw_data = raw_data.encode("utf-8")
        return hashlib.sha256(raw_data).hexdigest()

    def upsert_versioned_payload(
        self, payload
    ) -> Tuple[RawPayloadModel, str]:
        """Synchronizes a RawPayload with the database, returning (model, status).

        Status is one of:
            CREATED  - new payload, assigned version 1
            UPDATED  - content changed, old version deactivated, new vN+1 created
            UNCHANGED - content identical to current active version, no-op
        """
        content_hash = self.compute_hash(payload.raw_content)

        with self.SessionLocal() as session:
            stmt = (
                select(RawPayloadModel)
                .where(
                    RawPayloadModel.payload_id == payload.payload_id,
                    RawPayloadModel.is_active.is_(True),
                )
                .order_by(RawPayloadModel.version.desc())
            )
            existing = session.execute(stmt).scalar_one_or_none()

            if existing is None:
                new_payload = RawPayloadModel(
                    payload_id=payload.payload_id,
                    version=1,
                    file_hash=content_hash,
                    source_uri=payload.source_uri,
                    raw_content=payload.raw_content,
                    content_type=payload.content_type,
                    is_active=True,
                    is_deleted=False,
                )
                session.add(new_payload)
                session.commit()
                session.refresh(new_payload)
                logger.info(
                    "Created new payload version",
                    payload_id=payload.payload_id,
                    version=1,
                )
                return new_payload, "CREATED"

            if existing.file_hash == content_hash and not existing.is_deleted:
                logger.info(
                    "Payload content unchanged",
                    payload_id=payload.payload_id,
                    version=existing.version,
                )
                return existing, "UNCHANGED"

            existing.is_active = False
            next_version = existing.version + 1

            updated_payload = RawPayloadModel(
                payload_id=payload.payload_id,
                version=next_version,
                file_hash=content_hash,
                source_uri=payload.source_uri,
                raw_content=payload.raw_content,
                content_type=payload.content_type,
                is_active=True,
                is_deleted=False,
            )
            session.add(updated_payload)
            session.commit()
            session.refresh(updated_payload)
            logger.info(
                "Updated payload to new version",
                payload_id=payload.payload_id,
                new_version=next_version,
            )
            return updated_payload, "UPDATED"

    def sync_deleted_payloads(self, active_source_ids: List[str]) -> List[str]:
        """Marks payloads missing from active source scans as deleted and
        flags their associated chunks for purge.

        Returns a list of payload_ids that were soft-deleted.
        """
        with self.SessionLocal() as session:
            stmt = select(RawPayloadModel).where(
                RawPayloadModel.is_active.is_(True),
                RawPayloadModel.is_deleted.is_(False),
                RawPayloadModel.payload_id.not_in(active_source_ids),
            )
            stale_payloads = session.execute(stmt).scalars().all()
            deleted_ids: List[str] = []

            for payload in stale_payloads:
                payload.is_deleted = True
                payload.is_active = False
                deleted_ids.append(payload.payload_id)

                for doc in payload.parsed_documents:
                    for chunk in doc.chunks:
                        chunk.is_purged = True

            session.commit()
            if deleted_ids:
                logger.info(
                    "Soft-deleted missing payloads",
                    count=len(deleted_ids),
                    deleted_ids=deleted_ids,
                )
            return deleted_ids