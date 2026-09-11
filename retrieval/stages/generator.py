"""
retrieval/stages/generator.py
Formats retrieved context into system/user prompts and calls OpenAI chat completion endpoints to generate a grounded answer with cited chunk IDs.
"""

from typing import Any, Dict
from core.config import settings
from core.logging import get_logger
from core.pipeline import PipelineStage
from retrieval.stages.models import RetrievalResult, SynthesizedResponse

logger = get_logger(__name__)


class GeneratorStage(PipelineStage[RetrievalResult, SynthesizedResponse]):
    """
    Formats reranked context chunks and query into a prompt and generates a synthesized RAG response.
    """

    def __init__(self, model_name: str = "gpt-4o-mini", stage_name: str = "GeneratorStage"):
        super().__init__(stage_name=stage_name)
        self.model_name = model_name

    def _build_prompt(self, query: str, context_blocks: str) -> str:
        return f"""You are a precise technical AI assistant. Answer the user's question using ONLY the provided context snippets.
If the answer cannot be determined from the context, state that clearly.

--- CONTEXT SNIPPETS ---
{context_blocks}

--- QUESTION ---
{query}
"""

    def execute(self, input_data: RetrievalResult, context: Dict[str, Any]) -> SynthesizedResponse:
        query_text = input_data.query.raw_query
        chunks = input_data.chunks

        # Format context blocks with chunk IDs
        formatted_context = []
        for c in chunks:
            formatted_context.append(f"[{c.chunk_id}] ({c.metadata.get('title', 'Document')}):\n{c.chunk_text}")
        context_str = "\n\n".join(formatted_context) if formatted_context else "No relevant context found."

        prompt = self._build_prompt(query_text, context_str)
        generated_answer = ""

        if settings.OPENAI_API_KEY:
            try:
                import openai
                client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
                res = client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )
                generated_answer = res.choices[0].message.content.strip()
            except Exception as e:
                logger.error("LLM Generation failed", error=str(e))
                generated_answer = f"[Generation Error]: Failed to contact LLM provider: {str(e)}"
        else:
            generated_answer = f"Synthesized answer based on {len(chunks)} chunks (OpenAI key not configured)."

        logger.info("Generator stage completed")
        return SynthesizedResponse(
            query=query_text,
            answer=generated_answer,
            cited_chunks=chunks,
            execution_metadata={
                "model": self.model_name,
                "num_context_chunks": len(chunks),
            }
        )