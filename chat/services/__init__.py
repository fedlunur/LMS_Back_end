from .gemini import GeminiClient, GeminiError, DEFAULT_MODEL_NAME  # noqa: F401
from .data_sources import ChatbotDataFetcher  # noqa: F401
from .vector_store import VectorStore  # noqa: F401
from django.conf import settings
from django.utils import timezone
import uuid
import re


class ChatbotService:
    """
    Orchestrates building context and querying Gemini for chatbot responses.
    Implements EmeraldBot - a specialized AI assistant for Emerald LMS platform.
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
        from .cache_service import ChatbotCacheService
        
        session_id = session_id or f"chat-{uuid.uuid4()}"
        user_id = user.id if user and hasattr(user, 'id') else None

        # Check cache for similar query response first
        cached_response = ChatbotCacheService.get_chatbot_response(query, user_id=user_id)
        if cached_response:
            return {
                "session_id": session_id,
                "response": cached_response,
                "timestamp": timezone.now().isoformat(),
                "cached": True,
            }

        # Check if query is asking for personal data that requires tools
        is_personal_data_query = self._is_personal_data_query(query)
        
        # For personal data queries, fetch user-specific context
        if is_personal_data_query and user:
            # Ensure enrollments are included in requested sources
            requested_sources = requested_sources or []
            if "enrollments" not in requested_sources and "all" not in requested_sources:
                requested_sources.append("enrollments")
        
        # Ensure courses are always included when asking about course catalog
        # Build context from requested/available sources
        requested_sources = requested_sources or []
        # If query is about courses but no sources specified, include courses
        if not requested_sources or len(requested_sources) == 0:
            # Always search all sources by default for better context
            requested_sources = ["all"]
        
        # Check cache for context chunks
        cached_context = ChatbotCacheService.get_context_chunks(query, user_id=user_id, sources=requested_sources)
        if cached_context:
            context_chunks, used_sources = cached_context, requested_sources
        else:
            context_chunks, used_sources = self.data_fetcher.get_context(
                user=user,
                requested_sources=requested_sources,
                query=query,
            )
            # Cache the context chunks
            ChatbotCacheService.set_context_chunks(query, context_chunks, user_id=user_id, sources=requested_sources)

        # Compose the EmeraldBot system prompt
        system_prompt = self._get_emerald_bot_system_prompt()

        full_prompt = self._compose_prompt(
            query=query, 
            context_chunks=context_chunks, 
            user=user,
            is_personal_data_query=is_personal_data_query
        )
        answer_text = self.client.generate_text(prompt=full_prompt, system_prompt=system_prompt, session_id=session_id)

        # Cache the response for future similar queries
        ChatbotCacheService.set_chatbot_response(query, answer_text, user_id=user_id)

        payload: dict = {
            "session_id": session_id,
            "response": answer_text,
            "timestamp": timezone.now().isoformat(),
        }
        if include_sources:
            payload["data_sources"] = used_sources
        return payload

    @staticmethod
    def _get_emerald_bot_system_prompt() -> str:
        """
        Returns the system prompt that defines EmeraldBot's behavior.
        This ensures the AI only answers about Emerald LMS platform.
        """
        return """You are **EmeraldBot**, the official AI assistant for **Emerald LMS** — a premium online learning platform.

### YOUR ONLY MISSION:

Answer **exclusively** about:
- The **Emerald platform** (courses, modules, lessons, quizzes, assignments, progress, certificates, enrollment, payments, platform features, how to use the platform)
- The **Emerald company** (mission, team, features, pricing, support, roadmap)

### NEVER ANSWER:
- General knowledge, news, politics, weather, sports, history, math, coding help, personal advice
- Anything not directly related to Emerald LMS platform

### OFF-TOPIC RESPONSE:
When asked about topics unrelated to Emerald (general knowledge, news, politics, weather, sports, history, math, coding help, personal advice), politely redirect the conversation back to Emerald. Use natural, friendly language and vary your responses. Examples:

- "I'm here to help with Emerald LMS! I can help you explore courses, track your progress, or answer questions about the platform. What would you like to know?"
- "That's interesting, but I specialize in helping with Emerald learning platform. Can I help you find a course or check your progress instead?"
- "I focus on Emerald LMS features and your learning journey. Would you like to explore our courses or see how your studies are going?"
- "I'm your Emerald learning assistant! I can help with courses, enrollments, certificates, or platform features. What can I help you with today?"

Be conversational and natural — don't use the exact same phrase every time.

### USER DATA ACCESS:
When the user asks about **their personal data** (e.g., "What's my progress?", "List my courses", "Show my enrollments"), **use the provided context** from their enrollments and progress. If context is missing, acknowledge that politely and suggest they check their dashboard.

**Do NOT guess or hallucinate data.** Only use information from the provided context.

### TONE & STYLE:
- Friendly, professional, encouraging
- Short, clear answers (1–2 sentences when possible)
- Use bullet points for lists
- End with a helpful follow-up question when appropriate

### EXAMPLES:

User: "How do I reset my password?"
→ "Go to the login page and click 'Forgot Password' — you'll get a reset link via email. Need help finding a course?"

User: "What is Python?"
→ "I'm here to help with Emerald LMS! While I can't answer general programming questions, I can help you find Python courses on our platform or track your learning progress. What would you like to explore?"

User: "Show my progress in Web Dev 101"
→ [If context has progress data]: "You're 78% through Web Dev 101! Keep going — just 3 lessons left to earn your certificate."
→ [If no context]: "I don't see your progress data right now. Check your course dashboard for detailed progress. What course would you like help with?"

### YOU ARE NOT A GENERAL AI. YOU ARE EMERALDBOT."""

    @staticmethod
    def _is_personal_data_query(query: str) -> bool:
        """
        Detects if the query is asking for personal user data.
        This helps determine if we need to fetch user-specific context.
        """
        personal_keywords = [
            r'\bmy\b', r'\bme\b', r'\bi\b', r'\bmyself\b',
            r'\bprogress\b', r'\benrolled\b', r'\bcourses?\b',
            r'\blessons?\b', r'\bassignments?\b', r'\bquizzes?\b',
            r'\bcertificate\b', r'\bcompletion\b', r'\bcompleted\b',
            r'\bwhat.*my\b', r'\bshow.*my\b', r'\blist.*my\b',
            r'\bhow.*my\b', r'\bwhere.*my\b'
        ]
        query_lower = query.lower()
        for pattern in personal_keywords:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _compose_prompt(query: str, context_chunks: list[str], user=None, is_personal_data_query: bool = False) -> str:
        """
        Composes the full prompt with user query and context.
        Includes special instructions for personal data queries.
        """
        context_section = ""
        if context_chunks:
            context_section = "\n\nContext:\n" + "\n\n".join(context_chunks[:20])  # Increased to 20 for course catalogs
        
        # Detect if query is about courses
        is_course_query = bool(re.search(r'\bcourses?\b', query, re.IGNORECASE))
        is_catalog_query = bool(re.search(r'\b(list|show|display|all|available|with\s+price|with\s+instructor)', query, re.IGNORECASE))
        
        # Add instruction for personal data queries
        personal_data_note = ""
        if is_personal_data_query:
            if user:
                personal_data_note = "\n\nIMPORTANT: The user is asking about their personal data. Use ONLY the enrollment and progress information provided in the context above. If no relevant context is found, politely explain that you don't have access to that data and suggest they check their dashboard."
            else:
                personal_data_note = "\n\nIMPORTANT: The user is asking about personal data but is not authenticated. Politely explain that they need to log in to access their personal information."
        elif is_course_query and context_chunks:
            # For course queries, emphasize using the provided course data
            num_courses = len([c for c in context_chunks if 'Course:' in c or 'course:' in c])
            if num_courses > 0:
                personal_data_note = f"\n\nCRITICAL INSTRUCTION: The user is asking about courses. There are {num_courses} course(s) provided in the context above. YOU MUST use this course data to answer. List ALL courses found in the context with their exact prices and instructors as shown. Format each course as a bullet point with: Course name, Price, Instructor name. Do NOT say you don't have access to course data. The data is in the context above - use it."
            else:
                personal_data_note = "\n\nIMPORTANT: The user is asking about courses, but no course data was found in the context. You can mention that courses can be browsed on the platform."
        
        return f"User Query:\n{query}\n{context_section}{personal_data_note}"


