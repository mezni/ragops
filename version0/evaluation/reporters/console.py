"""
evaluation/reporters/console.py
Prints benchmark evaluation results formatted in ASCII console tables.
"""

from typing import Dict, Any


class ConsoleReporter:
    """Renders evaluation results to the terminal via Rich-style ASCII tables."""

    @staticmethod
    def print_report(eval_output: Dict[str, Any]) -> None:
        """Print a formatted benchmark report to stdout."""
        summary = eval_output.get("summary", {})
        detailed = eval_output.get("detailed_results", [])

        print("==========================================================")
        print("                RAG EVALUATION BENCHMARK                  ")
        print("==========================================================")
        print(f"Total Test Cases Evaluated : {summary.get('total_test_cases', 0)}")
        print(f"Mean Reciprocal Rank (MRR): {summary.get('mean_mrr', 0.0):.4f}")
        print(f"Hit Rate                   : {summary.get('mean_hit_rate', 0.0):.4f}")
        print(f"Context Precision          : {summary.get('mean_context_precision', 0.0):.4f}")
        print(f"Context Recall             : {summary.get('mean_context_recall', 0.0):.4f}")
        print(f"Faithfulness               : {summary.get('mean_faithfulness', 0.0):.4f}")
        print(f"Answer Relevance           : {summary.get('mean_answer_relevance', 0.0):.4f}")
        print("----------------------------------------------------------")

        for item in detailed:
            print(f"[Case {item['case_id']}] Question: {item['question']}")
            print(f"  └─ Latency: {item['latency_seconds']}s")
            print(f"  └─ Precision: {item['retrieval_metrics']['context_precision']} | Recall: {item['retrieval_metrics']['context_recall']}")
            print(f"  └─ Faithfulness: {item['generation_metrics']['faithfulness']}")
            print("----------------------------------------------------------")