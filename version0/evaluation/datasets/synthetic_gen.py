"""
evaluation/datasets/synthetic_gen.py
Synthetically generates evaluation ground truth dataset pairs (Question, Answer, Chunks)
using LLM text extraction over chunk collections.
"""

import json
from typing import List, Dict, Any


def generate_synthetic_dataset(chunks: List[Dict[str, Any]], output_file: str) -> None:
    """Generates synthetic QA test cases from chunk collections."""
    synthetic_cases = []

    for idx, chunk in enumerate(chunks):
        chunk_id = chunk.get("chunk_id", f"chunk_{idx}")
        chunk_text = chunk.get("chunk_text", "")
        payload_id = chunk.get("payload_id", "")

        # Heuristic/LLM synthetic question generator mock structure
        question = f"What key information is described in chunk {chunk_id}?"
        answer = f"The content states: {chunk_text[:100]}..."

        synthetic_cases.append(
            {
                "id": f"syn_eval_{idx+1}",
                "question": question,
                "expected_payload_id": payload_id,
                "expected_context_chunks": [chunk_id],
                "ground_truth_answer": answer,
            }
        )

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(synthetic_cases, f, indent=2)

    print(f"✅ Generated {len(synthetic_cases)} synthetic test cases saved to {output_file}")


if __name__ == "__main__":
    sample_chunks = [
        {"chunk_id": "c1", "payload_id": "p1", "chunk_text": "Qdrant supports scalable vector payload isolation."},
        {"chunk_id": "c2", "payload_id": "p2", "chunk_text": "Cross-encoders rerank documents for increased accuracy."},
    ]
    generate_synthetic_dataset(sample_chunks, "evaluation/datasets/synthetic_truth.json")