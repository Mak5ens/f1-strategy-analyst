"""Deterministic tools: typed functions that compute, so that numbers never come from a model.

A tool validates its input against a Pydantic model and returns another one. The input model's JSON schema is
what a model sees in tool calling; the output is what the agent quotes and what its verification checks.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class ToolError(Exception):
    """The request cannot be answered from the data (unknown driver, session not ingested...).

    The message is meant for the caller, model or human: it says what is missing, never a stack trace.
    """


@dataclass(frozen=True)
class Tool[In: BaseModel, Out: BaseModel]:
    name: str
    description: str
    input_model: type[In]
    output_model: type[Out]
    function: Callable[[In], Out]

    def run(self, arguments: In | dict[str, Any]) -> Out:
        """Validate the arguments (a model, or the JSON a model produced), then compute."""
        request = arguments if isinstance(arguments, self.input_model) else self.input_model.model_validate(arguments)
        return self.function(request)

    def openai_schema(self) -> dict[str, Any]:
        """The tool in the `tools` format of the OpenAI API, which the gateway forwards to every model."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_model.model_json_schema(),
            },
        }
