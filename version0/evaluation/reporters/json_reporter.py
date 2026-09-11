"""
evaluation/reporters/json_reporter.py
Exports benchmark results to structured JSON reports for CI/CD tracking.
"""

import json
from typing import Dict, Any


class JSONReporter:
    """Writes evaluation output to a JSON file for automated tracking."""

    @staticmethod
    def export(eval_output: Dict[str, Any], output_path: str) -> None:
        """Writes evaluation summary and itemized results to a JSON file.

        Args:
            eval_output: Dict with "summary" and "detailed_results" keys.
            output_path: Path to write the JSON report to.
        """
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(eval_output, f, indent=2)
        print(f"✅ Evaluation benchmark report exported to {output_path}")