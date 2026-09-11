from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, text

from core.logging import get_logger
from loaders.base import BaseSourceLoader, RawPayload

logger = get_logger(__name__)


class DatabaseLoader(BaseSourceLoader):
    """Executes a SQL query against a database and converts rows into RawPayload objects."""

    def __init__(
        self,
        connection_url: str,
        query: str,
        id_column: str,
        content_column: str,
        source_name: str = "relational_db"
    ):
        self.engine = create_engine(connection_url, pool_pre_ping=True)
        self.query = query
        self.id_column = id_column
        self.content_column = content_column
        self.source_name = source_name

    def load(self) -> List[RawPayload]:
        payloads: List[RawPayload] = []

        with self.engine.connect() as connection:
            result = connection.execute(text(self.query))
            rows = result.mappings().all()

            for row in rows:
                row_dict = dict(row)
                payload_id = str(row_dict.get(self.id_column))
                content = str(row_dict.get(self.content_column, ""))

                if not payload_id or not content:
                    logger.warning("Skipping row with missing ID or content", row=row_dict)
                    continue

                payload = RawPayload(
                    payload_id=f"{self.source_name}::{payload_id}",
                    source_type="database",
                    source_uri=f"sql://{self.source_name}/{payload_id}",
                    raw_content=content,
                    content_type="text/plain",
                    metadata={"raw_row": row_dict}
                )
                payloads.append(payload)

        logger.info("Database loading completed", total_loaded=len(payloads))
        return payloads