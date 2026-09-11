from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, TypeVar

I = TypeVar("I")
O = TypeVar("O")


class PipelineStage(Generic[I, O], ABC):
    """Abstract base for indexing pipeline stages sharing an execution context."""

    def __init__(self, stage_name: str = "PipelineStage"):
        self.stage_name = stage_name

    @abstractmethod
    def execute(self, input_data: I, context: Dict[str, Any]) -> O:
        """Transforms pipeline input into pipeline output given a shared context."""
        pass

    def __call__(self, input_data: I, context: Dict[str, Any]) -> O:
        return self.execute(input_data, context)


class GeneralizedPipeline(Generic[I, O]):
    """Orchestrates sequential execution of PipelineStage instances.

    Input flows through each stage in order; every stage's output becomes the
    next stage's input. A shared ``context`` dict (e.g. holding ``db_manager``)
    is passed to every stage.
    """

    def __init__(self, name: str, stages: List[PipelineStage]):
        self.name = name
        self.stages = stages

    def run(self, initial_input: I, context: Dict[str, Any]) -> O:
        data = initial_input
        for stage in self.stages:
            data = stage.execute(data, context)
        return data

    def __call__(self, initial_input: I, context: Dict[str, Any]) -> O:
        return self.run(initial_input, context)