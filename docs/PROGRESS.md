# Step Tracker — RAG Indexing Pipeline

A phased engineering ledger tracking every problem, design choice, and bottleneck across the development lifecycle. Each step follows the template below, copied for every new step (Step 0.1, Step 0.2, Step 1.1, ...), aligned with `execution_plan.md` phases.

## Template (copy for each new step)

| Field | Details |
|-------|---------|
| **Step ID & Name** | `Step X.Y: <short name>` |
| **Phase** | `<Setup / Indexing / Resilience / Testing / ...>` |
| **Files Modified** | `<created or modified files>` |
| **Problem** | `<why this step is necessary>` |
| **Approach** | `<design decision + tech used>` |
| **Result** | `<target outcome → result obtained>` |
| **Next** | `<next step or known blocker>` |

---

## Current Steps

| Step ID | Step Name | Phase | Problem | Approach | Result | Next |
|---------|-----------|-------|---------|----------|--------|------|
| **0.1** | Project Bootstrap | Setup | Pas de squelette exécutable — impossible de tester une stage sans config ni connexion DB partagées. | PipelineConfig (Pydantic) comme source unique de config ; engine SQLAlchemy avec pool de connexions ; migration 0 = activation de l'extension vector. | Visé : docker-compose up démarre Postgres+pgvector, pipeline db upgrade passe sans erreur. Obtenu : *(à renseigner)* | Détection des changements filesystem (Step 1.1 — Phase 1 de execution_plan.md) |
| **1.1** | Filesystem Change Detection | Indexing | Détecter les nouveaux/modifiés fichiers `data/raw/` et déclencher le re-ingestion. | Observer les timestamps/fingerprints des fichiers ; comparaison avec l'historique stocké en DB. | *(à renseigner)* | Parsing et formatage des .txt et .pdf documents (Step 2.1) |
| **2.1** | Document Parsing | Indexing | Parser les .txt simples et les .pdf multi-colonnes sans perdre le contexte des tableaux de taux. | Utilise les parsers texte/pyPDF avec extraction de tableaux ; enrichissement metadata (source, version, page). | *(à renseigner)* | Chunking sémantique avec fenêtre glissante (Step 3.1) |
| **3.1** | Semantic Chunking | Indexing | Découper le texte en chunks significatifs (500 tokens, chevauchement 50 tokens) sans couper les phrases en half. | Fenêtre glissante adaptative par unité sémantique ; préservation des qualificatifs (ex: "Fee waived if paid within 5 days"). | *(à renseigner)* | Génération d'embeddings et stockage ChromaDB (Step 4.1) |
| **4.1** | Embeddings & ChromaDB Storage | Indexing | Embedder chaque chunk et persister dans ChromaDB local avec métadonnées riches. | OpenAI text-embedding-3-small lorsque OPENAI_API_KEY est défini ; fallback deterministe hashlib.md5 sinon. | *(à renseigner)* | Recherche similarité vecteur (retrieval.py — Step 5.1) |
| **5.1** | Vector Similarity Search | Résilience | Recherche nearest-neighbor sur les requêtes utilisateur avec filtres metadata (is_active, version, tenant). | ChromaDB vector store avec recherche dense + filtres payload ; top-K context formatting. | *(à renseigner)* | Synthèse LLM et génération de réponses ancrées (Step 6.1) |
| **6.1** | LLM Synthesis | Évaluation | Synthétiser une réponse ancrée (grounded) à partir des chunks récupérés, avec zéro hallucination de taux/coûts. | Prompt template gardé ; vérification groundedness contre le contexte récupéré ; métriques RAG Triad. | *(à renseigner)* | Boucle d'évaluation continue CI/CD |

---

## Phase Reference

| Phase | Description |
|-------|-------------|
| **Setup** | Initial project scaffolding, configuration, database initialization |
| **Indexing** | Document ingestion, parsing, chunking, embedding storage |
| **Resilience** | Vector search reliability, caching, error handling, recovery |
| **Testing** | Unit tests, integration tests, evaluation benchmarks (RAG Triad) |
| **Evaluation** | Continuous quality monitoring, CI/CD integration, performance tuning |