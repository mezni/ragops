"""
app/streamlit_app.py
Main entry point for the Streamlit dashboard app.
Sets configuration, global themes, and renders system telemetry.
"""

import streamlit as st

st.set_page_config(
    page_title="Versioned RAG Control Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    st.title("⚡ Versioned RAG Control Center")
    st.caption("Production-Grade Modular RAG Platform with Versioned Ingestion & Evaluation")

    st.markdown("---")

    # Overview Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(label="Vector Store Status", value="Connected", delta="Qdrant Active")
    with col2:
        st.metric(label="Payload Isolation", value="Enforced", delta="is_active=True")
    with col3:
        st.metric(label="Reranker Model", value="MiniLM-L-6-v2", delta="Cross-Encoder")
    with col4:
        st.metric(label="LLM Synthesis", value="GPT-4o-Mini", delta="Grounding Active")

    st.markdown("---")

    st.markdown(
        """
        ### Welcome to the Management Console
        Select a tool from the sidebar navigation menu:

        * **🔍 Search & Chat**: Interactively execute vector retrieval queries, view reranked scores, and inspect cited payload versions.
        * **📂 Document Manager**: Upload documents, manage ingestion pipeline tasks, and toggle payload versions.
        * **📊 Evaluation Dashboard**: Run quality benchmarks (Context Precision, Context Recall, Faithfulness) and export reports.
        """
    )


if __name__ == "__main__":
    main()