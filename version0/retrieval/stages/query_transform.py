"""
retrieval/stages/query_transform.py
Rewrites and expands incoming queries to improve retrieval context matching.
"""

from typing import Any, Dict
from core.config import settings
from core.logging import get_logger
from core.pipeline import PipelineStage
from retrieval.stages.models import Query

logger = get_logger(__name__)


class QueryTransformStage(PipelineStage[Query, Query]):
    """
    Transforms the raw user query by applying rewriting rules, HyDE generation,
    or normalization prior to vector retrieval.
    """

    def __init__(self, mode: str = "rewrite", stage_name: str = "QueryTransformStage"):
        super().__init__(stage_name=stage_name)
        self.mode = mode

    def _generate_hyde_document(self, query_text: str) -> str:
        """Generates a hypothetical answer document using an LLM to align vector space."""
        if settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Generate a short, hypothetical document snippet that directly answers the question. "
                                       "Do not include conversational filler."
                        },
                        {"role": "user", "content": query_text}
                    ],
                    max_tokens=150,
                    temperature=0.3,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("HyDE generation failed, falling back to original query", error=str(e))

        return query_text

    def execute(self, input_data: Query, context: Dict[str, Any]) -> Query:
        logger.debug("Executing QueryTransformStage", raw_query=input_data.raw_query, mode=self.mode)

        if self.mode == "hyde":
            input_data.transformed_query = self._generate_hyde_document(input_data.raw_query)
        else:
            # Basic normalization (stripping white space and trailing symbols)
            input_data.transformed_query = input_data.raw_query.strip().rstrip("?")

        logger.info("Query transformation completed", transformed=input_data.transformed_query)
        return input_data