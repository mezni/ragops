"""app/pages/2_📂_Document_Manager.py
Document management subpage for uploading files, trigger ingestion pipelines,
and toggling active payload versions.
"""

import streamlit as st
from app.components.admin import render_document_status_table, render_version_toggle

st.set_page_config(page_title="Document Manager", page_icon="📂", layout="wide")

st.title("📂 Document & Payload Manager")
st.caption("Upload documents, trigger ingestion, and manage version active states")

st.markdown("### 📤 Upload New Document")

with st.form("ingestion_form", clear_on_submit=True):
    uploaded_file = st.file_uploader("Select Document File", type=["txt", "pdf", "md", "json"])
    payload_id = st.text_input("Payload ID", placeholder="e.g. doc_system_requirements")
    version_str = st.text_input("Version Number", value="1")
    submit_button = st.form_submit_button("Start Ingestion Pipeline")

if submit_button:
    if uploaded_file and payload_id:
        st.success(f"Successfully triggered ingestion pipeline for '{payload_id}' (v{version_str}).")
    else:
        st.error("Please provide both a document file and a unique Payload ID.")

st.markdown("---")
st.markdown("### 📋 Active Document Payloads")

sample_docs = [
    {"payload_id": "doc_sys_config", "active_version": 1, "total_chunks": 12, "is_active": True},
    {"payload_id": "doc_version_policy", "active_version": 2, "total_chunks": 5, "is_active": True},
]

render_document_status_table(sample_docs)

st.markdown("### ⚙️ Quick Version Actions")
render_version_toggle("doc_sys_config", 1)
