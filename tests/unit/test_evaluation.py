"""
tests/unit/test_evaluation.py
Unit tests for evaluation pipeline: metrics, builder, and reporters.
"""

import json
import tempfile
import os

import pytest

from evaluation.metrics.retrieval_eval import evaluate_retrieval
from evaluation.metrics.generation_eval import evaluate_generation
from evaluation.builder import EvaluationPipeline
from evaluation.reporters.console import ConsoleReporter
from evaluation.reporters.json_reporter import JSONReporter


class TestRetrievalMetrics:
    def test_evaluate_retrieval_full_match(self):
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1", "chunk_2"],
            expected_chunk_ids=["chunk_1", "chunk_2"],
        )
        assert result["hit_rate"] == 1.0
        assert result["mrr"] == 1.0
        assert result["context_precision"] == 1.0
        assert result["context_recall"] == 1.0

    def test_evaluate_retrieval_no_match(self):
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1", "chunk_2"],
            expected_chunk_ids=["chunk_3", "chunk_4"],
        )
        assert result["hit_rate"] == 0.0
        assert result["mrr"] == 0.0
        assert result["context_precision"] == 0.0
        assert result["context_recall"] == 0.0

    def test_evaluate_retrieval_empty_expected(self):
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1"],
            expected_chunk_ids=[],
        )
        assert result["hit_rate"] == 1.0
        assert result["mrr"] == 1.0
        assert result["context_precision"] == 1.0
        assert result["context_recall"] == 1.0

    def test_evaluate_retrieval_partial_match(self):
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1", "chunk_2", "chunk_3"],
            expected_chunk_ids=["chunk_1", "chunk_2"],
        )
        assert result["hit_rate"] == 1.0
        assert result["mrr"] == 1.0 / 1  # first chunk matches at rank 1
        assert result["context_precision"] == round(2.0 / 3, 4)  # 2 hits / 3 retrieved
        assert result["context_recall"] == round(2.0 / 2, 4)  # 2 hits / 2 expected


class TestGenerationMetrics:
    def test_evaluate_generation_with_answer(self):
        result = evaluate_generation(
            generated_answer="The cat sat on the mat",
            retrieved_contexts=["the cat is on the mat", "dog runs"],
            ground_truth="The cat sat on the mat",
        )
        assert "faithfulness" in result
        assert "answer_relevance" in result
        assert result["faithfulness"] > 0.0
        assert result["answer_relevance"] > 0.0

    def test_evaluate_generation_empty_answer(self):
        result = evaluate_generation(
            generated_answer="",
            retrieved_contexts=["some context"],
            ground_truth="some ground truth",
        )
        assert result["faithfulness"] == 0.0
        assert result["answer_relevance"] == 0.0


class TestEvaluationPipeline:
    def test_pipeline_instantiation(self):
        pipeline = EvaluationPipeline()
        assert pipeline is not None
        assert hasattr(pipeline, "run_eval")
        assert hasattr(pipeline, "_compute_summary")

    def test_compute_summary_with_results(self):
        pipeline = EvaluationPipeline()
        results = [
            {
                "case_id": "case_1",
                "retrieval_metrics": {"mrr": 0.8, "hit_rate": 0.9, "context_precision": 0.7, "context_recall": 0.6},
                "generation_metrics": {"faithfulness": 0.9, "answer_relevance": 0.8},
            },
            {
                "case_id": "case_2",
                "retrieval_metrics": {"mrr": 0.6, "hit_rate": 0.5, "context_precision": 0.4, "context_recall": 0.3},
                "generation_metrics": {"faithfulness": 0.5, "answer_relevance": 0.3},
            },
        ]
        summary = pipeline._compute_summary(results)
        assert summary["total_test_cases"] == 2
        assert summary["mean_mrr"] == round((0.8 + 0.6) / 2, 4)
        assert summary["mean_hit_rate"] == round((0.9 + 0.5) / 2, 4)


class TestConsoleReporter:
    def test_print_report_has_summary(self):
        output = {
            "summary": {
                "total_test_cases": 1,
                "mean_mrr": 0.85,
                "mean_hit_rate": 0.9,
                "mean_context_precision": 0.88,
                "mean_context_recall": 0.82,
                "mean_faithfulness": 0.91,
                "mean_answer_relevance": 0.89,
            },
            "detailed_results": [
                {
                    "case_id": "eval_001",
                    "question": "What is Qdrant?",
                    "latency_seconds": 1.234,
                    "retrieval_metrics": {"context_precision": 0.9, "context_recall": 0.85},
                    "generation_metrics": {"faithfulness": 0.95},
                }
            ],
        }

        # Should not raise
        ConsoleReporter.print_report(output)

    def test_print_report_empty(self):
        ConsoleReporter.print_report({"summary": {}, "detailed_results": []})


class TestJSONReporter:
    def test_export_creates_valid_json(self):
        output = {
            "summary": {"total_test_cases": 1, "mean_mrr": 0.85},
            "detailed_results": [
                {"case_id": "eval_001", "question": "test", "latency_seconds": 1.0}
            ],
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            JSONReporter.export(output, tmp_path)
            with open(tmp_path, "r") as f:
                loaded = json.load(f)
            assert "summary" in loaded
            assert "detailed_results" in loaded
        finally:
            os.unlink(tmp_path)

    def test_export_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            JSONReporter.export({}, tmp_path)
            with open(tmp_path, "r") as f:
                loaded = json.load(f)
            assert loaded == {}
        finally:
            os.unlink(tmp_path)