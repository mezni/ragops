"""
app/pages/3_📊_Evaluation.py
Dashboard subpage to trigger quality benchmarks and render evaluation metrics.
"""

import streamlit as st
from evaluation.builder import EvaluationPipeline
from evaluation.reporters.console import ConsoleReporter

st.set_page_config(page_title="Evaluation", page_icon="📊", layout="wide")

st.title("📊 RAG Quality Benchmark Dashboard")
st.caption("Run context recall, context precision, and faithfulness evaluations")

dataset_file = st.text_input("Ground Truth Dataset Path", value="evaluation/datasets/ground_truth.json")

if st.button("🚀 Run Quality Benchmark", type="primary"):
    with st.spinner("Executing batch benchmark evaluation..."):
        try:
            eval_pipeline = EvaluationPipeline()
            eval_output = eval_pipeline.run_eval(dataset_file)
            summary = eval_output.get("summary", {})

            st.success("Benchmark Run Complete!")

            # Display Key Metric Cards
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Context Precision", f"{summary.get('mean_context_precision', 0.0):.4f}")
            c2.metric("Context Recall", f"{summary.get('mean_context_recall', 0.0):.4f}")
            c3.metric("Faithfulness", f"{summary.get('mean_faithfulness', 0.0):.4f}")
            c4.metric("Mean MRR", f"{summary.get('mean_mrr', 0.0):.4f}")

            st.markdown("### 📝 Itemized Case Results")
            st.json(eval_output.get("detailed_results", []))

        except Exception as e:
            st.error(f"Failed to execute evaluation pipeline: {str(e)}")