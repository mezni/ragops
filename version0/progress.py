"""Progress tracking for the Aether Wireless RAG Pipeline.

Provides a step tracker aligned with docs/PROGRESS.md and execution_plan.md phases.
Used by ingestion.py and retrieval.py to report pipeline state during execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    SETUP = "Setup"
    INDEXING = "Indexing"
    RESILIENCE = "Resilience"
    TESTING = "Testing"
    EVALUATION = "Evaluation"


@dataclass
class Step:
    id: str
    name: str
    phase: Phase
    problem: str
    approach: str
    result: Optional[str] = None
    next_step: Optional[str] = None

    def mark_complete(self, result: str, next_step: Optional[str] = None) -> None:
        self.result = result
        self.next_step = next_step


@dataclass
class ProgressTracker:
    """Tracks progress through the RAG indexing pipeline steps."""

    steps: dict[str, Step] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)

    def add_step(self, step: Step) -> None:
        self.steps[step.id] = step

    def complete_step(self, step_id: str, result: str, next_step: Optional[str] = None) -> None:
        if step_id not in self.steps:
            msg = f"Step {step_id} not found in tracker"
            raise ValueError(msg)
        self.steps[step_id].mark_complete(result, next_step)
        self.completed.add(step_id)

    def get_step(self, step_id: str) -> Step:
        if step_id not in self.steps:
            msg = f"Step {step_id} not found in tracker"
            raise ValueError(msg)
        return self.steps[step_id]

    def list_steps(self) -> list[Step]:
        return list(self.steps.values())

    def list_completed(self) -> list[Step]:
        return [s for s in self.steps.values() if s.id in self.completed]


# Pre-configured steps aligned with docs/PROGRESS.md and execution_plan.md
INITIAL_STEPS = [
    Step(
        id="0.1",
        name="Project Bootstrap",
        phase=Phase.SETUP,
        problem="Pas de squelette exécutable — impossible de tester une stage sans config ni connexion DB partagées.",
        approach="PipelineConfig (Pydantic) comme source unique de config ; engine SQLAlchemy avec pool de connexions ; migration 0 = activation de l'extension vector.",
        result=None,
        next_step="1.1 — Détection des changements filesystem (Phase 1 de execution_plan.md)",
    ),
    Step(
        id="1.1",
        name="Filesystem Change Detection",
        phase=Phase.INDEXING,
        problem="Detecter les nouveaux/modifiés fichiers data/raw/ et déclencher le re-ingestion.",
        approach="Observer les timestamps/fingerprints des fichiers ; comparaison avec l'historique stocké en DB.",
        result=None,
        next_step="2.1 — Parsing et formatage des .txt et .pdf documents",
    ),
    Step(
        id="2.1",
        name="Document Parsing",
        phase=Phase.INDEXING,
        problem="Parser les .txt simples et les .pdf multi-colonnes sans perdre le contexte des tableaux de taux.",
        approach="Utilise les parsers texte/pyPDF avec extraction de tableaux ; enrichissement metadata (source, version, page).",
        result=None,
        next_step="3.1 — Chunking sémantique avec fenêtre glissante",
    ),
    Step(
        id="3.1",
        name="Semantic Chunking",
        phase=Phase.INDEXING,
        problem=" Découper le texte en chunks significatifs (500 tokens, chevauchement 50 tokens) sans couper les phrases en half.",
        approach="Fenêtre glissante adaptative par unité sémantique ; préservation des qualificatifs (ex: 'Fee waived if paid within 5 days').",
        result=None,
        next_step="4.1 — Génération d'embeddings et stockage ChromaDB",
    ),
    Step(
        id="4.1",
        name="Embeddings & ChromaDB Storage",
        phase=Phase.INDEXING,
        problem="Embedder chaque chunk et persister dans ChromaDB local avec métadonnées riches.",
        approach="OpenAI text-embedding-3-small lorsque OPENAI_API_KEY est défini ; fallback deterministe hashlib.md5 sinon.",
        result=None,
        next_step="5.1 — Vecteur recherche similarité (retrieval.py)",
    ),
    Step(
        id="5.1",
        name="Vector Similarity Search",
        phase=Phase.RESILIENCE,
        problem="Recherche nearest-neighbor sur les requêtes utilisateur avec filtres metadata (is_active, version, tenant).",
        approach="ChromaDB vector store avec recherche dense + filtres payload ; top-K context formatting.",
        result=None,
        next_step="6.1 — LLM synthesis and grounded answer generation",
    ),
    Step(
        id="6.1",
        name="LLM Synthesis",
        phase=Phase.EVALUATION,
        problem="Synthétiser une réponse ancrée (grounded) à partir des chunks récupérés, avec zéro hallucination de taux/coûts.",
        approach="Prompt template gardé ; vérification groundedness contre le contexte récupéré ; métriques RAG Triad.",
        result=None,
        next_step="Boucle d'évaluation continue CI/CD",
    ),
]

__all__ = ["Phase", "Step", "ProgressTracker", "INITIAL_STEPS"]