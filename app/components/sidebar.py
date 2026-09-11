"""
app/components/sidebar.py
Reusable sidebar widget for controlling search parameters and version filters.
"""

from typing import Any, Dict, Tuple
import streamlit as st


def render_sidebar() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Renders reusable sidebar options and returns query settings and filters."""
    st.sidebar.header("⚙️ Pipeline Controls")

    transform_mode = st.sidebar.selectbox(
        "Query Transform Strategy",
        options=["rewrite", "hyde"],
        index=0,
        help="Select query transformation algorithm.",
    )

    top_k = st.sidebar.slider(
        "Initial Vector Search (top_k)",
        min_value=1,
        max_value=20,
        value=5,
    )

    rerank_top_n = st.sidebar.slider(
        "Cross-Encoder Rerank (top_n)",
        min_value=1,
        max_value=10,
        value=3,
    )

    st.sidebar.markdown("---")
    st.sidebar.header("🔒 Payload Version Filters")

    payload_id = st.sidebar.text_input(
        "Payload ID Filter",
        value="",
        placeholder="e.g. doc_sys_config",
    )

    payload_version_str = st.sidebar.text_input(
        "Payload Version Filter",
        value="",
        placeholder="e.g. 1",
    )

    pipeline_settings = {
        "transform_mode": transform_mode,
        "top_k": top_k,
        "rerank_top_n": rerank_top_n,
    }

    filters = {}
    if payload_id.strip():
        filters["payload_id"] = payload_id.strip()
    if payload_version_str.strip() and payload_version_str.strip().isdigit():
        filters["version"] = int(payload_version_str.strip())

    return pipeline_settings, filters