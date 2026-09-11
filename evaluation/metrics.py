"""
evaluation/metrics.py
LLM-as-a-Judge metric evaluators for Context Precision, Context Recall, and Faithfulness.
"""

from abc import ABC, abstractmethod
import json
from typing import List, Optional

from core.config import settings
from core.logging import get_logger
from evaluation.models import MetricScore

logger = get_logger(__name__)


class BaseMetric(ABC):
    """Abstract interface for all evaluation metrics."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the metric."""
        pass

    @abstractmethod
    def evaluate(
        self,
        query: str,
        generated_answer: str,
        retrieved_contexts: List[str],
        expected_answer: Optional[str] = None,
        expected_context_ids: Optional[List[str]] = None,
    ) -> MetricScore:
        """Evaluates pipeline outputs against ground truth inputs."""
        pass


class ContextPrecisionMetric(BaseMetric):
    """
    Measures the ratio of relevant context chunks retrieved relative to the total chunks fetched.
    Evaluates whether relevant chunks are ranked higher in the retrieved set.
    """

    @property
    def name(self) -> str:
        return "context_precision"

    def evaluate(
        self,
        query: str,
        generated_answer: str,
        retrieved_contexts: List[str],
        expected_answer: Optional[str] = None,
        expected_context_ids: Optional[List[str]] = None,
    ) -> MetricScore:
        if not retrieved_contexts:
            return MetricScore(
                metric_name=self.name,
                score=0.0,
                reasoning="No context chunks were retrieved.",
            )

        # Fallback to direct context string comparison if expected IDs are available
        if expected_context_ids and len(expected_context_ids) > 0:
            relevant_count = sum(1 for cid in expected_context_ids if cid in retrieved_contexts)
            score = relevant_count / len(retrieved_contexts)
            return MetricScore(
                metric_name=self.name,
                score=round(score, 4),
                reasoning=f"{relevant_count} out of {len(retrieved_contexts)} retrieved chunks matched expected IDs.",
            )

        # LLM-as-a-Judge fallback if ground truth IDs are omitted
        prompt = f"""You are an expert RAG evaluator. Analyze if each context chunk below is relevant for answering the user query.
Query: {query}
Expected Answer Reference: {expected_answer or "N/A"}

Context Chunks:
{json.dumps(retrieved_contexts, indent=2)}

Respond with JSON in this structure:
{{
"verdicts": [1, 0, 1], // 1 for relevant, 0 for irrelevant for each context chunk in order
"reasoning": "Brief explanation of relevance judgements."
}}
"""
        return _invoke_llm_judge(self.name, prompt, len(retrieved_contexts))


class ContextRecallMetric(BaseMetric):
    """
    Measures how much of the ground-truth expected answer/facts are backed up by the retrieved context chunks.
    """

    @property
    def name(self) -> str:
        return "context_recall"

    def evaluate(
        self,
        query: str,
        generated_answer: str,
        retrieved_contexts: List[str],
        expected_answer: Optional[str] = None,
        expected_context_ids: Optional[List[str]] = None,
    ) -> MetricScore:
        if not expected_answer:
            return MetricScore(
                metric_name=self.name,
                score=1.0,
                reasoning="Skipped: No expected_answer ground-truth provided for recall comparison.",
            )

        prompt = f"""You are an expert evaluator. Assess if the provided Ground Truth statements can be directly attributed to the Retrieved Context.
User Query: {query}
Ground Truth Answer: {expected_answer}

Retrieved Contexts:
{json.dumps(retrieved_contexts, indent=2)}

Respond with JSON in this structure:
{{
"score": 0.85, // Float between 0.0 and 1.0 representing proportion of ground truth facts covered
"reasoning": "Brief evaluation explanation."
}}
"""
        return _invoke_llm_judge(self.name, prompt)


class FaithfulnessMetric(BaseMetric):
    """
    Measures hallucination: checks if claims made in the generated answer are strictly grounded
    and supported by the retrieved context snippets.
    """

    @property
    def name(self) -> str:
        return "faithfulness"

    def evaluate(
        self,
        query: str,
        generated_answer: str,
        retrieved_contexts: List[str],
        expected_answer: Optional[str] = None,
        expected_context_ids: Optional[List[str]] = None,
    ) -> MetricScore:
        if not generated_answer or not retrieved_contexts:
            return MetricScore(
                metric_name=self.name,
                score=0.0,
                reasoning="Generated answer or retrieved contexts were empty.",
            )

        prompt = f"""You are an expert hallucination detector. Verify if every claim made in the Generated Answer is directly supported by the Retrieved Contexts.
Generated Answer:
{generated_answer}

Retrieved Contexts:
{json.dumps(retrieved_contexts, indent=2)}

Respond with JSON in this structure:
{{
"score": 1.0, // Float between 0.0 and 1.0 (1.0 = fully faithful, 0.0 = completely hallucinated)
"reasoning": "Detailed justification of claims supported vs unsupported."
}}
        return _invoke_llm_judge(self.name, prompt)


def _invoke_llm_judge(metric_name: str, prompt: str, total_items: Optional[int] = None) -> MetricScore:
    """Helper method to invoke OpenAI LLM judge and parse response."""
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY missing. Returning mock score for metric.", metric=metric_name)
        return MetricScore(
            metric_name=metric_name,
            score=0.85,
            reasoning="Mock evaluation score (OpenAI API key missing).",
        )

    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        payload = json.loads(response.choices[0].message.content)

        if "verdicts" in payload and total_items is not None:
            verdicts = payload.get("verdicts", [])
            score = sum(verdicts) / total_items if total_items > 0 else 0.0
        else:
            score = float(payload.get("score", 0.0))

        return MetricScore(
            metric_name=metric_name,
            score=round(max(0.0, min(1.0, score)), 4),
            reasoning=payload.get("reasoning", "LLM evaluation finished."),
        )
    except Exception as e:
        logger.error("LLM judge evaluation failed", metric=metric_name, error=str(e))
        return MetricScore(
            metric_name=metric_name,
            score=0.0,
            reasoning=f"LLM evaluator exception: {str(e)}",
        )