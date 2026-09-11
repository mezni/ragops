"""Data contracts and structures for evaluation test cases, metric results,
and benchmark reporting."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvalTestCase(BaseModel):
    """
    Represents a single ground-truth test sample for evaluation.
    """
    test_id: str
    user_query: str
    expected_answer: Optional[str] = None
    expected_context_ids: List[str] = Field(default_factory=list)
    filters: Dict[str, Any] = Field(default_factory=dict)


class MetricScore(BaseModel):
    """
    Individual score and reasoning produced by a metric evaluator.
    """
    metric_name: str
    score: float  # Value between 0.0 and 1.0
    reasoning: Optional[str] = None


class EvalResult(BaseModel):
    """
    Evaluation output for a single test case across all computed metrics.
    """
    test_id: str
    user_query: str
    generated_answer: str
    retrieved_chunk_ids: List[str] = Field(default_factory=list)
    metric_scores: Dict[str, MetricScore] = Field(default_factory=dict)
    execution_time_seconds: float = 0.0


class EvaluationReport(BaseModel):
    """
    Aggregated benchmark report across an entire test dataset run.
    """
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_test_cases: int
    mean_scores: Dict[str, float] = Field(default_factory=dict)
    detailed_results: List[EvalResult] = Field(default_factory=list)