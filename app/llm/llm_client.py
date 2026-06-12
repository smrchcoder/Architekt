from __future__ import annotations

import os
from typing import TYPE_CHECKING, Type, TypeVar

import instructor
from app.core.config import settings

if TYPE_CHECKING:
    from instructor import Instructor

T = TypeVar("T")

# Map provider names to their from_provider model string prefixes.
# format: "provider/model-name" — instructor resolves the rest automatically.
_PROVIDER_PREFIXES: dict[str, str] = {
    "openai": "openai",
    "gemini": "google",
}


class LLMClient:
    """Provider-agnostic wrapper for structured LLM extraction via instructor.

    Uses `instructor.from_provider()` (v1.15.1+) which automatically selects
    the correct mode (TOOLS vs JSON) and handles provider-specific edge cases
    — including nested schema support for Gemini.

    Lazy-initialised: the underlying client is only created on first use,
    so importing this module does not require valid API keys at startup.
    """

    def __init__(self) -> None:
        self.provider: str = settings.llm_provider
        self.model: str = settings.llm_model
        self._client: Instructor | None = None  # lazy

    def _get_client(self) -> Instructor:
        """Build and cache the instructor client on first call."""
        if self._client is not None:
            return self._client

        if self.provider == "openai":
            # Inject the key into the environment so the openai SDK picks it up.
            # from_provider("openai/...") reads OPENAI_API_KEY from env automatically.
            if settings.openai_api_key:
                os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
            self._client = instructor.from_provider(f"openai/{self.model}")

        elif self.provider == "gemini":
            # from_provider("google/...") uses the google-generativeai SDK natively.
            # This supports complex nested Pydantic schemas correctly — the compat
            # URL workaround does not.
            if settings.gemini_api_key:
                os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
            self._client = instructor.from_provider(f"google/{self.model}")

        else:
            raise ValueError(
                f"Unsupported LLM_PROVIDER: '{self.provider}'. "
                "Supported values: 'openai', 'gemini'."
            )

        return self._client

    def extract_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        # Number of times instructor will retry Pydantic *validation* failures
        # by re-prompting the model with the specific validation error.
        # This is NOT the same as network/API retry — that is handled by the
        # underlying SDK (openai/google-generativeai) automatically.
        validation_retries: int = 2,
    ) -> T:
        """Call the LLM and return a validated, fully-typed Pydantic object.

        Args:
            system_prompt:      The system instructions (role + rules + schema).
            user_prompt:        The user message (article text + task).
            response_model:     The Pydantic model class to parse into.
            validation_retries: How many times to re-prompt if the LLM returns
                                JSON that fails Pydantic validation.

        Returns:
            A fully validated instance of `response_model`.
        """
        client = self._get_client()
        return client.chat.completions.create(
            model=self.model,
            response_model=response_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,  # Always 0 for factual extraction; increases to ~0.4 for Story generation
            max_retries=validation_retries,
        )
