from __future__ import annotations

import os
from typing import TYPE_CHECKING, Type, TypeVar

import instructor
from app.core.config import settings

if TYPE_CHECKING:
    from instructor import Instructor

T = TypeVar("T")


class LLMClient:
    """Provider-agnostic wrapper for structured LLM extraction via instructor.

    Supports per-call model overrides by caching clients per model name,
    so extraction and sections can target different model tiers.
    """

    def __init__(self) -> None:
        self.provider: str = settings.llm_provider
        self.model: str = settings.llm_model
        self._clients: dict[str, Instructor] = {}

    def _get_client(self, model: str | None = None) -> Instructor:
        resolved = model or self.model
        if resolved in self._clients:
            return self._clients[resolved]

        if self.provider == "openai":
            if settings.openai_api_key:
                os.environ["OPENAI_API_KEY"] = settings.openai_api_key
            client = instructor.from_provider(f"openai/{resolved}")

        elif self.provider == "gemini":
            if settings.gemini_api_key:
                os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
            client = instructor.from_provider(f"google/{resolved}")

        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER: '{self.provider}'. "
                "Supported values: 'openai', 'gemini'."
            )

        self._clients[resolved] = client
        return client

    def extract_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float = 0.0,
        validation_retries: int = 2,
        model: str | None = None,
    ) -> T:
        """Call the LLM and return a validated, fully-typed Pydantic object.

        Args:
            system_prompt:      The system instructions (role + rules + schema).
            user_prompt:        The user message (article text + task).
            response_model:     The Pydantic model class to parse into.
            validation_retries: How many times to re-prompt if the LLM returns
                                JSON that fails Pydantic validation.
            model:              Override the default model for this call.

        Returns:
            A fully validated instance of `response_model`.
        """
        client = self._get_client(model)
        return client.chat.completions.create(
            model=model or self.model,
            response_model=response_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_retries=validation_retries,
        )
