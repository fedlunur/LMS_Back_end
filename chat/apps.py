from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'

    def ready(self):
        """
        Called when Django starts. Use this to pre-load expensive resources
        like the embedding model so they're ready before first request.
        """
        try:
            # Pre-load embedding model in a background thread to avoid blocking startup
            import threading
            
            def preload_model():
                try:
                    import time
                    # Wait for server to fully start to avoid fighting for resources during startup
                    time.sleep(30)
                    
                    from .services.vector_store import get_embedding_model
                    logger.info("Pre-loading embedding model (background)...")
                    get_embedding_model()  # This will cache the model globally
                    logger.info("Embedding model pre-loaded successfully.")
                except Exception as e:
                    logger.warning(f"Failed to pre-load embedding model: {e}. It will load on first use.")
            
            # Start pre-loading in background thread
            thread = threading.Thread(target=preload_model, daemon=True)
            thread.start()
            logger.info("Started background thread for embedding model pre-loading.")
        except Exception as e:
            logger.warning(f"Could not start embedding model pre-loading: {e}")
