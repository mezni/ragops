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

    def test_evaluate_retrieval_single_retrieved_match(self):
        """When only 1 chunk is retrieved and it matches."""
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1"],
            expected_chunk_ids=["chunk_1"],
        )
        assert result["hit_rate"] == 1.0
        assert result["mrr"] == 1.0  # rank 1 -> 1/1
        assert result["context_precision"] == 1.0  # 1/1
        assert result["context_recall"] == 1.0  # 1/1

    def test_evaluate_retrieval_single_retrieved_no_match(self):
        """When only 1 chunk is retrieved and it doesn't match."""
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1"],
            expected_chunk_ids=["chunk_2"],
        )
        assert result["hit_rate"] == 0.0
        assert result["mrr"] == 0.0
        assert result["context_precision"] == 0.0  # 0/1
        assert result["context_recall"] == 0.0  # 0/1

    def test_evaluate_retrieval_all_retrieved_match(self):
        """When all retrieved chunks match and there are no extra."""
        result = evaluate_retrieval(
            retrieved_chunk_ids=["chunk_1", "chunk_2"],
            expected_chunk_ids=["chunk_1", "chunk_2"],
        )
        assert result["hit_rate"] == 1.0
        assert result["mrr"] == 1.0 / 1  # first at rank 1
        assert result["context_precision"] == 1.0  # 2/2
        assert result["context_recall"] == 1.0  # 2/2


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

    def test_evaluate_generation_no_ground_truth(self):
        """When ground_truth is empty string."""
        result = evaluate_generation(
            generated_answer="Some answer",
            retrieved_contexts=["some context"],
            ground_truth="",
        )
        assert "faithfulness" in result
        assert "answer_relevance" in result

    def test_evaluate_generation_no_contexts(self):
        """When retrieved_contexts is empty."""
        result = evaluate_generation(
            generated_answer="Some answer",
            retrieved_contexts=[],
            ground_truth="some ground truth",
        )
        assert "faithfulness" in result
        assert "answer_relevance" in result


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
        assert summary["mean_context_precision"] == round((0.7 + 0.4) / 2, 4)
        assert summary["mean_context_recall"] == round((0.6 + 0.3) / 2, 4)
        assert summary["mean_faithfulness"] == round((0.9 + 0.5) / 2, 4)
        assert summary["mean_answer_relevance"] == round((0.8 + 0.3) / 2, 4)

    def test_compute_summary_empty(self):
        pipeline = EvaluationPipeline()
        summary = pipeline._compute_summary([])
        assert summary == {}


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

    def test_print_report_missing_keys(self):
        """Test reporter handles missing keys gracefully."""
        ConsoleReporter.print_report({"summary": {}, "detailed_results": []})

    def test_print_report_partial_summary(self):
        """Test reporter with partial summary keys."""
        ConsoleReporter.print_report({
            "summary": {"total_test_cases": 1},
            "detailed_results": [],
        })


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

    def test_export_partial_output(self):
        """Test reporter with partial output dict."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            JSONReporter.export({"summary": {"total_test_cases": 1}}, tmp_path)
            with open(tmp_path, "r") as f:
                loaded = json.load(f)
            assert loaded == {"summary": {"total_test_cases": 1}}
        finally:
            os.unlink(tmp_path)