"""
Redis caching service for chatbot performance optimization.
Caches responses, course data, and context to reduce latency.
"""
import json
import hashlib
from typing import Optional, Dict, Any
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

# Cache timeout values (in seconds)
CACHE_TIMEOUTS = {
    'chatbot_response': 3600,  # 1 hour for similar queries
    'course_catalog': 1800,     # 30 minutes for course lists
    'user_enrollments': 300,    # 5 minutes for user data
    'context_chunks': 600,      # 10 minutes for context
    'vector_search': 1800,      # 30 minutes for vector search results
}


class ChatbotCacheService:
    """
    Redis-based caching service for chatbot performance optimization.
    """

    @staticmethod
    def _generate_cache_key(prefix: str, *args, **kwargs) -> str:
        """Generate a consistent cache key from arguments."""
        # Create a string representation of all arguments
        key_parts = [prefix]
        
        # Add positional arguments
        for arg in args:
            if arg is not None:
                key_parts.append(str(arg))
        
        # Add keyword arguments sorted by key
        for key in sorted(kwargs.keys()):
            value = kwargs[key]
            if value is not None:
                key_parts.append(f"{key}:{value}")
        
        # Join and hash for consistent length
        key_string = "::".join(key_parts)
        
        # Hash if too long (Redis keys have size limits)
        if len(key_string) > 200:
            key_string = hashlib.md5(key_string.encode()).hexdigest()
            key_parts = [prefix, key_string]
        
        return "::".join(key_parts)

    @staticmethod
    def get_chatbot_response(query: str, user_id: Optional[int] = None) -> Optional[str]:
        """
        Get cached chatbot response for a query.
        Normalizes query for better cache hit rate.
        """
        # Normalize query (lowercase, strip whitespace)
        normalized_query = query.lower().strip()
        
        cache_key = ChatbotCacheService._generate_cache_key(
            'chatbot:response',
            normalized_query,
            user_id=user_id
        )
        
        try:
            cached = cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT for chatbot response: {query[:50]}")
                return cached
            logger.debug(f"Cache MISS for chatbot response: {query[:50]}")
            return None
        except Exception as e:
            logger.warning(f"Error getting cached response: {e}")
            return None

    @staticmethod
    def set_chatbot_response(query: str, response: str, user_id: Optional[int] = None):
        """
        Cache chatbot response.
        """
        normalized_query = query.lower().strip()
        
        cache_key = ChatbotCacheService._generate_cache_key(
            'chatbot:response',
            normalized_query,
            user_id=user_id
        )
        
        try:
            cache.set(cache_key, response, timeout=CACHE_TIMEOUTS['chatbot_response'])
            logger.debug(f"Cached chatbot response: {query[:50]}")
        except Exception as e:
            logger.warning(f"Error caching response: {e}")

    @staticmethod
    def get_course_catalog() -> Optional[list]:
        """
        Get cached course catalog data.
        """
        cache_key = 'chatbot:courses:catalog'
        
        try:
            cached = cache.get(cache_key)
            if cached:
                logger.debug("Cache HIT for course catalog")
                return cached
            return None
        except Exception as e:
            logger.warning(f"Error getting cached course catalog: {e}")
            return None

    @staticmethod
    def set_course_catalog(courses_data: list):
        """
        Cache course catalog data.
        """
        cache_key = 'chatbot:courses:catalog'
        
        try:
            cache.set(cache_key, courses_data, timeout=CACHE_TIMEOUTS['course_catalog'])
            logger.debug(f"Cached {len(courses_data)} courses")
        except Exception as e:
            logger.warning(f"Error caching course catalog: {e}")

    @staticmethod
    def get_user_enrollments(user_id: int) -> Optional[list]:
        """
        Get cached user enrollment data.
        """
        cache_key = f'chatbot:enrollments:user:{user_id}'
        
        try:
            cached = cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT for user {user_id} enrollments")
                return cached
            return None
        except Exception as e:
            logger.warning(f"Error getting cached enrollments: {e}")
            return None

    @staticmethod
    def set_user_enrollments(user_id: int, enrollments_data: list):
        """
        Cache user enrollment data.
        """
        cache_key = f'chatbot:enrollments:user:{user_id}'
        
        try:
            cache.set(cache_key, enrollments_data, timeout=CACHE_TIMEOUTS['user_enrollments'])
            logger.debug(f"Cached enrollments for user {user_id}")
        except Exception as e:
            logger.warning(f"Error caching enrollments: {e}")

    @staticmethod
    def get_context_chunks(query: str, user_id: Optional[int] = None, sources: Optional[list] = None) -> Optional[list]:
        """
        Get cached context chunks for a query.
        """
        normalized_query = query.lower().strip()
        sources_str = ",".join(sorted(sources or []))
        
        cache_key = ChatbotCacheService._generate_cache_key(
            'chatbot:context',
            normalized_query,
            user_id=user_id,
            sources=sources_str
        )
        
        try:
            cached = cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT for context chunks: {query[:50]}")
                return cached
            return None
        except Exception as e:
            logger.warning(f"Error getting cached context: {e}")
            return None

    @staticmethod
    def set_context_chunks(query: str, chunks: list, user_id: Optional[int] = None, sources: Optional[list] = None):
        """
        Cache context chunks for a query.
        """
        normalized_query = query.lower().strip()
        sources_str = ",".join(sorted(sources or []))
        
        cache_key = ChatbotCacheService._generate_cache_key(
            'chatbot:context',
            normalized_query,
            user_id=user_id,
            sources=sources_str
        )
        
        try:
            cache.set(cache_key, chunks, timeout=CACHE_TIMEOUTS['context_chunks'])
            logger.debug(f"Cached context chunks for query: {query[:50]}")
        except Exception as e:
            logger.warning(f"Error caching context chunks: {e}")

    @staticmethod
    def invalidate_user_cache(user_id: int):
        """
        Invalidate all cached data for a user (e.g., when enrollments change).
        """
        try:
            # Invalidate user enrollments
            cache_key = f'chatbot:enrollments:user:{user_id}'
            cache.delete(cache_key)
            
            # Invalidate user-specific responses (use pattern matching if available)
            # Note: Django cache doesn't support pattern matching, so we'd need to track keys
            logger.info(f"Invalidated cache for user {user_id}")
        except Exception as e:
            logger.warning(f"Error invalidating user cache: {e}")

    @staticmethod
    def invalidate_course_catalog():
        """
        Invalidate course catalog cache (e.g., when courses are added/updated).
        """
        try:
            cache_key = 'chatbot:courses:catalog'
            cache.delete(cache_key)
            logger.info("Invalidated course catalog cache")
        except Exception as e:
            logger.warning(f"Error invalidating course catalog cache: {e}")

