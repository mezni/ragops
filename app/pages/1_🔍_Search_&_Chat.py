"""
app/pages/1_🔍_Search_&_Chat.py
RAG interactive chat interface.
"""

import streamlit as st
from app.components.sidebar import render_sidebar
from app.components.chat import render_cited_chunks
from retrieval.builder import build_retrieval_pipeline
from retrieval.stages.models import Query, SynthesizedResponse

st.set_page_config(page_title="Search & Chat", page_icon="🔍", layout="wide")

st.title("🔍 Search & Chat Interface")

# Render Sidebar Widgets
settings, filters = render_sidebar()

# Session State History Initialization
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Display Messages
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
    if "cited_chunks" in msg:
        render_cited_chunks(msg["cited_chunks"])

# User Prompt Processing
user_input = st.chat_input("Ask a question based on indexed payloads...")

if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Processing retrieval query..."):
            try:
                pipeline = build_retrieval_pipeline(
                    transform_mode=settings["transform_mode"],
                    rerank_top_n=settings["rerank_top_n"],
                )
                query_obj = Query(raw_query=user_input, top_k=settings["top_k"], filters=filters)
                response: SynthesizedResponse = pipeline.run(query_obj)

                st.write(response.answer)

                cited_data = [
                    {
                        "chunk_id": c.chunk_id,
                        "payload_version": c.payload_version,
                        "score": c.score,
                        "rerank_score": f"{c.rerank_score:.4f}" if c.rerank_score is not None else "N/A",
                        "chunk_text": c.chunk_text,
                    }
                    for c in response.cited_chunks
                ]

                render_cited_chunks(cited_data)

                st.session_state["messages"].append(
                    {
                        "role": "assistant",
                        "content": response.answer,
                        "cited_chunks": cited_data,
                    }
                )
            except Exception as e:
                st.error(f"Execution Error: {str(e)}")