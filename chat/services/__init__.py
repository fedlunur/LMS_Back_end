from .gemini import GeminiClient, GeminiError, DEFAULT_MODEL_NAME  # noqa: F401
from .data_sources import ChatbotDataFetcher  # noqa: F401
from .vector_store import VectorStore  # noqa: F401
from django.conf import settings
from django.utils import timezone
import uuid


class ChatbotService:
    """
    Orchestrates building context and querying Gemini for chatbot responses.
    """

    def __init__(self):
        model_name = getattr(settings, "GEMINI_MODEL_NAME", DEFAULT_MODEL_NAME)
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        self.client = GeminiClient(api_key=api_key, model_name=model_name)
        self.data_fetcher = ChatbotDataFetcher()

    def handle_query(
        self,
        query: str,
        session_id: str | None = None,
        user=None,
        include_sources: bool = False,
        requested_sources: list[str] | None = None,
    ) -> dict:
        session_id = session_id or f"chat-{uuid.uuid4()}"

        # Build context from requested/available sources
        requested_sources = requested_sources or []
        context_chunks, used_sources = self.data_fetcher.get_context(
            user=user,
            requested_sources=requested_sources,
            query=query,
        )

        system_prompt = (
            "You are Emerald LMS assistant. Answer clearly, concisely, and helpfully. "
            "Use provided context when relevant. If unsure or context is missing, say so briefly."
        )

        full_prompt = self._compose_prompt(query=query, context_chunks=context_chunks)
        answer_text = self.client.generate_text(prompt=full_prompt, system_prompt=system_prompt, session_id=session_id)

        payload: dict = {
            "session_id": session_id,
            "response": answer_text,
            "timestamp": timezone.now().isoformat(),
        }
        if include_sources:
            payload["data_sources"] = used_sources
        return payload

    @staticmethod
    def _compose_prompt(query: str, context_chunks: list[str]) -> str:
        context_section = ""
        if context_chunks:
            context_section = "\n\nContext:\n" + "\n\n".join(context_chunks[:10])
        return f"User Query:\n{query}\n{context_section}"


