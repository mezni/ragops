"""
app/components/admin.py
Reusable UI tables and management controls for document payloads and versions.
"""

from typing import Any, Dict, List
import streamlit as st


def render_document_status_table(documents: List[Dict[str, Any]]) -> None:
    """Renders document status dataframe/table."""
    if not documents:
        st.info("No documents indexed in vector store.")
        return

    st.dataframe(
        documents,
        column_config={
            "payload_id": "Payload ID",
            "active_version": "Active Version",
            "total_chunks": "Chunk Count",
            "is_active": "Status",
        },
        use_container_width=True,
    )


def render_version_toggle(payload_id: str, current_version: int) -> None:
    """Renders action buttons to activate or roll back versions."""
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Activate Version {current_version}", key=f"act_{payload_id}"):
            st.success(f"Updated {payload_id} to active version {current_version}")
    with col2:
        if st.button(f"Deactivate {payload_id}", key=f"deact_{payload_id}"):
            st.warning(f"Deactivated {payload_id}")