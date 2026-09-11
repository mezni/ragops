"""
evaluation/metrics/retrieval_eval.py
Computes retrieval quality metrics: Hit Rate, MRR (Mean Reciprocal Rank),
Context Precision, and Context Recall.
"""

from typing import List, Dict, Any


def evaluate_retrieval(
    retrieved_chunk_ids: List[str],
    expected_chunk_ids: List[str],
) -> Dict[str, float]:
    """Computes exact-match metrics between retrieved chunks and expected ground truth chunks."""
    if not expected_chunk_ids:
        return {
            "hit_rate": 1.0,
            "mrr": 1.0,
            "context_precision": 1.0,
            "context_recall": 1.0,
        }

    expected_set = set(expected_chunk_ids)

    # 1. Hit Rate
    hits = [cid for cid in retrieved_chunk_ids if cid in expected_set]
    hit_rate = 1.0 if len(hits) > 0 else 0.0

    # 2. MRR (Mean Reciprocal Rank)
    mrr = 0.0
    for rank, cid in enumerate(retrieved_chunk_ids, start=1):
        if cid in expected_set:
            mrr = 1.0 / rank
            break

    # 3. Context Precision (Relevant retrieved chunks / Total retrieved chunks)
    total_retrieved = len(retrieved_chunk_ids)
    context_precision = len(hits) / total_retrieved if total_retrieved > 0 else 0.0

    # 4. Context Recall (Relevant retrieved chunks / Total expected chunks)
    context_recall = len(hits) / len(expected_set) if len(expected_set) > 0 else 0.0

    return {
        "hit_rate": round(hit_rate, 4),
        "mrr": round(mrr, 4),
        "context_precision": round(context_precision, 4),
        "context_recall": round(context_recall, 4),
    }