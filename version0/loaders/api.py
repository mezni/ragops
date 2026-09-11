from typing import Any, Dict, List, Optional
import requests

from core.logging import get_logger
from loaders.base import BaseSourceLoader, RawPayload

logger = get_logger(__name__)


class APILoader(BaseSourceLoader):
    """Fetches text resources from REST API endpoints."""

    def __init__(
        self,
        endpoint_url: str,
        id_key: str,
        content_key: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 30
    ):
        self.endpoint_url = endpoint_url
        self.id_key = id_key
        self.content_key = content_key
        self.headers = headers or {}
        self.params = params or {}
        self.timeout = timeout

    def load(self) -> List[RawPayload]:
        payloads: List[RawPayload] = []

        try:
            response = requests.get(
                self.endpoint_url,
                headers=self.headers,
                params=self.params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            items = data if isinstance(data, list) else data.get("items", [data])

            for item in items:
                item_id = str(item.get(self.id_key))
                content = str(item.get(self.content_key, ""))

                if not item_id or not content:
                    continue

                payload = RawPayload(
                    payload_id=f"api::{item_id}",
                    source_type="api",
                    source_uri=f"{self.endpoint_url}#{item_id}",
                    raw_content=content,
                    content_type="application/json",
                    metadata={"api_endpoint": self.endpoint_url, "raw_item": item}
                )
                payloads.append(payload)

        except requests.RequestException as e:
            logger.error("API loading failed", url=self.endpoint_url, error=str(e))
            raise e

        logger.info("API loading completed", total_loaded=len(payloads))
        return payloads