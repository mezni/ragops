"""
evaluation/metrics/generation_eval.py
Evaluates synthesized answer properties: Faithfulness (hallucination detection)
and Answer Relevance.
"""

from typing import List, Dict, Any


def evaluate_generation(
    generated_answer: str,
    retrieved_contexts: List[str],
    ground_truth: str,
) -> Dict[str, float]:
    """Computes generation metrics (Faithfulness & Answer Relevance)."""
    if not generated_answer:
        return {"faithfulness": 0.0, "answer_relevance": 0.0}

    combined_context = " ".join(retrieved_contexts).lower()
    answer_words = set(generated_answer.lower().split())

    # 1. Faithfulness Score (Lexical overlap heuristic with context)
    if answer_words:
        grounded_words = [w for w in answer_words if w in combined_context]
        faithfulness = len(grounded_words) / len(answer_words)
    else:
        faithfulness = 0.0

    # 2. Answer Relevance Score (Overlap heuristic with ground truth answer)
    gt_words = set(ground_truth.lower().split())
    if gt_words:
        relevant_words = [w for w in answer_words if w in gt_words]
        answer_relevance = len(relevant_words) / len(gt_words)
    else:
        answer_relevance = 1.0

    return {
        "faithfulness": round(min(faithfulness, 1.0), 4),
        "answer_relevance": round(min(answer_relevance, 1.0), 4),
    }