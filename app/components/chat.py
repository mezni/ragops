"""
app/components/chat.py
Reusable chat UI components for rendering chat messages and citations.
"""

from typing import Any, Dict, List
import streamlit as st


def render_chat_message(role: str, content: str) -> None:
    """Renders a single chat bubble."""
    with st.chat_message(role):
        st.write(content)


def render_cited_chunks(cited_chunks: List[Dict[str, Any]]) -> None:
    """Renders formatted expander listing cited context metadata."""
    if not cited_chunks:
        return

    with st.expander("📚 View Cited Context Chunks"):
        for chunk in cited_chunks:
            chunk_id = chunk.get("chunk_id", "N/A")
            version = chunk.get("payload_version", "N/A")
            score = chunk.get("score", 0.0)
            rerank_score = chunk.get("rerank_score", "N/A")
            text = chunk.get("chunk_text", "")

            st.markdown(
                f"**Chunk ID:** `{chunk_id}` | "
                f"**Version:** `{version}` | "
                f"**Vector Score:** `{score:.4f}` | "
                f"**Rerank Score:** `{rerank_score}`"
            )
            st.text(text)
            st.markdown("---")