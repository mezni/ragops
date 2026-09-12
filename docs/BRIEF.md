# Discovery Brief: Aether Wireless RAG Pipeline

## Customer
**Aether Wireless** — A regional telecommunications provider offering fiber internet, mobile plans, and enterprise network solutions.

## Target Users
1. **Tier-1 Customer Support Agents:** Need fast, precise answers to customer inquiries about plan specs, billing terms, and troubleshooting.
2. **End-Subscribers:** Self-service portal users seeking direct answers regarding their service terms and policies.

## Current Workflows
* Agents manually search through scattered static documents (`.txt` policy files, multi-column `.pdf` rate cards, and technical spec sheets) stored in legacy network shares.
* Customer support requests take 3–5 minutes per lookup while agents cross-reference multiple policy files during live calls or chats.

## Pain Points
* **High Resolution Latency:** Manual lookup bogs down support queues and inflates Average Handling Time (AHT).
* **Information Fragmentation:** Critical rules (e.g., promotional period expiration dates or overage fee exemptions) are split across multiple files.
* **Inconsistent Responses:** Human errors in reading complex rate matrices lead to agents quoting outdated or incorrect plan rates to customers.

## Systems Involved
* **Data Sources:** Local/Shared file directories (`data/raw/` containing `.txt` and `.pdf` files).
* **Ingestion Engine:** `src/ingestion/` (Local loader, recursive chunker, vector database indexing).
* **Retrieval Engine:** `retrieval.py` (Dense vector search, context formatter, LLM synthesis).
* **Vector Store & Embeddings:** Persistent ChromaDB instance powered by OpenAI / Sentence-Transformers embeddings.

## Constraints
* **Phase 1 Infrastructure:** Must run locally using Python scripts without external SaaS database dependencies.
* **Format Heterogeneity:** Pipeline must handle plain text files as well as complex multi-column PDF tables without losing context.
* **Groundedness:** Zero tolerance for hallucinated plan rates or non-existent policy claims.

## Success Metrics
* **Search Speed:** Context retrieval latency \(< 300\text{ms}\).
* **Retrieval Precision:** Precision @ \(K \ge 85\%\) for top retrieved context blocks.
* **Resolution Accuracy:** Zero price/fee hallucinations on standard policy test suites.
Business Value
Lower Operational Costs: Cuts support agent Average Handling Time (AHT) by an estimated 40% through instant context retrieval.

Reduced Churn: Eliminates customer frustration caused by conflicting agent answers and incorrect billing explanations.

Scalable Onboarding: Reduces training time for new support staff from weeks to days by centralizing knowledge retrieval into a single AI interface.