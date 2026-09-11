"""
evaluation/builder.py
Assembles the end-to-end evaluation runner to test RAG pipelines
against dataset test cases and execute configured metric scorers.
"""

import json
import time
from typing import Any, Dict, List, Optional
from retrieval.builder import build_retrieval_pipeline
from retrieval.stages.models import Query, SynthesizedResponse
from evaluation.metrics.retrieval_eval import evaluate_retrieval
from evaluation.metrics.generation_eval import evaluate_generation


class EvaluationPipeline:
    def __init__(
        self,
        transform_mode: str = "rewrite",
        rerank_top_n: int = 3,
        vector_store_adapter: Optional[Any] = None,
    ):
        self.retrieval_pipeline = build_retrieval_pipeline(
            vector_store_adapter=vector_store_adapter,
            transform_mode=transform_mode,
            rerank_top_n=rerank_top_n,
        )

    def run_eval(self, dataset_path: str) -> Dict[str, Any]:
        """Runs batch evaluation over a dataset JSON file."""
        with open(dataset_path, "r", encoding="utf-8") as f:
            test_cases = json.load(f)

        results: List[Dict[str, Any]] = []

        for idx, test_case in enumerate(test_cases):
            query_text = test_case["question"]
            expected_payload_id = test_case.get("expected_payload_id")
            expected_chunks = test_case.get("expected_context_chunks", [])
            ground_truth_answer = test_case.get("ground_truth_answer", "")

            # Construct system Query object
            filters = {}
            if expected_payload_id:
                filters["payload_id"] = expected_payload_id

            query_obj = Query(raw_query=query_text, top_k=5, filters=filters)

            start_time = time.time()
            response: SynthesizedResponse = self.retrieval_pipeline.run(query_obj)
            latency = time.time() - start_time

            # Extract retrieved information
            retrieved_chunk_ids = [c.chunk_id for c in response.cited_chunks]
            retrieved_texts = [c.chunk_text for c in response.cited_chunks]

            # 1. Calculate Retrieval Metrics
            retrieval_metrics = evaluate_retrieval(
                retrieved_chunk_ids=retrieved_chunk_ids,
                expected_chunk_ids=expected_chunks,
            )

            # 2. Calculate Generation Metrics
            generation_metrics = evaluate_generation(
                generated_answer=response.answer,
                retrieved_contexts=retrieved_texts,
                ground_truth=ground_truth_answer,
            )

            results.append(
                {
                    "case_id": test_case.get("id", f"case_{idx+1}"),
                    "question": query_text,
                    "generated_answer": response.answer,
                    "ground_truth": ground_truth_answer,
                    "latency_seconds": round(latency, 3),
                    "retrieval_metrics": retrieval_metrics,
                    "generation_metrics": generation_metrics,
                }
            )

        # Aggregate summary scores
        summary = self._compute_summary(results)

        return {
            "summary": summary,
            "detailed_results": results,
        }

    def _compute_summary(self, results: List[Dict[str, Any]]) -> Dict[str, float]:
        if not results:
            return {}

        total = len(results)
        mrr_sum = sum(r["retrieval_metrics"]["mrr"] for r in results)
        hit_rate_sum = sum(r["retrieval_metrics"]["hit_rate"] for r in results)
        precision_sum = sum(r["retrieval_metrics"]["context_precision"] for r in results)
        recall_sum = sum(r["retrieval_metrics"]["context_recall"] for r in results)

        faithfulness_sum = sum(r["generation_metrics"]["faithfulness"] for r in results)
        relevance_sum = sum(r["generation_metrics"]["answer_relevance"] for r in results)

        return {
            "total_test_cases": total,
            "mean_mrr": round(mrr_sum / total, 4),
            "mean_hit_rate": round(hit_rate_sum / total, 4),
            "mean_context_precision": round(precision_sum / total, 4),
            "mean_context_recall": round(recall_sum / total, 4),
            "mean_faithfulness": round(faithfulness_sum / total, 4),
            "mean_answer_relevance": round(relevance_sum / total, 4),
        }