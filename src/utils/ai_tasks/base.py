from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from src.utils.ai_client import AgyClient

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class AgyTask(ABC, Generic[InputT, OutputT]):
    """Base class representing a task to be processed via AgyClient.

    Encapsulates preprocessing, prompt rendering, execution, and postprocessing.
    """

    def __init__(
        self,
        model: str = "Gemini 3.5 Flash (High)",
        client: AgyClient | None = None,
    ):
        self.model = model
        self.client = client or AgyClient(model=model)

    def execute(self, *args: Any, **kwargs: Any) -> OutputT:
        """Executes the task step-by-step using the Template Method pattern."""
        input_data = self.preprocess(*args, **kwargs)
        prompt = self.render_prompt(input_data)
        raw_output = self.client.generate(prompt)
        return self.postprocess(raw_output, input_data)

    def preprocess(self, *args: Any, **kwargs: Any) -> InputT:
        """Processes raw inputs into the structured input data required by the task."""
        if len(args) == 1 and not kwargs:
            return args[0]  # type: ignore
        return kwargs  # type: ignore

    @abstractmethod
    def render_prompt(self, input_data: InputT) -> str:
        """Renders the final prompt string using the input data."""
        pass

    def postprocess(self, raw_output: str, input_data: InputT) -> OutputT:
        """Parses, cleanses, or validates the raw LLM output into the final output format."""
        return raw_output  # type: ignore
