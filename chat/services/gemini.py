from typing import Optional
import os
from django.core.exceptions import ImproperlyConfigured

DEFAULT_MODEL_NAME = "gemini-1.5-flash"


class GeminiError(Exception):
    pass


class GeminiClient:
    """
    Thin wrapper around google-generativeai text generation.
    """

    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_MODEL_NAME):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ImproperlyConfigured("GEMINI_API_KEY is not configured.")
        self.model_name = model_name

        try:
            import google.generativeai as genai  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise ImproperlyConfigured(
                "google-generativeai package is not installed. Add 'google-generativeai' to requirements.txt"
            ) from exc

        genai.configure(api_key=self.api_key)
        self._genai = genai
        # Store system prompt to be used when creating model instances
        self._system_prompt = None

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, session_id: Optional[str] = None) -> str:
        try:
            # Create model with system instruction if provided
            if system_prompt:
                model = self._genai.GenerativeModel(
                    self.model_name,
                    system_instruction=system_prompt
                )
            else:
                model = self._genai.GenerativeModel(self.model_name)
            
            # Generate content with just the user prompt
            response = model.generate_content(prompt)
            text = getattr(response, "text", "") or ""
            return text.strip()
        except Exception as exc:
            raise GeminiError(f"Gemini generation failed: {exc}") from exc


