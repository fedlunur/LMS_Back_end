"""
Vector store service for semantic search using ChromaDB.
Stores and retrieves embeddings of course content, FAQs, announcements, etc.
"""
import os
from typing import List, Dict, Optional, Tuple
from django.conf import settings
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

# Global cache for embedding model (loaded once)
_embedding_model_cache = None
_vector_store_instance = None


def get_vector_store():
    """Get or create singleton VectorStore instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance


def get_embedding_model():
    """Get or create cached embedding model."""
    global _embedding_model_cache
    if _embedding_model_cache is None:
        model_name = getattr(settings, "EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        try:
            _embedding_model_cache = SentenceTransformer(model_name)
            logger.info(f"Loaded embedding model: {model_name} (cached)")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    return _embedding_model_cache


class VectorStore:
    """
    Manages vector embeddings and semantic search for LMS content.
    Uses ChromaDB for storage and sentence-transformers for embeddings.
    """

    def __init__(self):
        # Use cached embedding model (loaded once, reused)
        self.embedding_model = get_embedding_model()

        # Initialize ChromaDB client
        persist_directory = getattr(settings, "CHROMA_DB_PATH", os.path.join(settings.BASE_DIR, "chroma_db"))
        os.makedirs(persist_directory, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="lms_content",
            metadata={"description": "LMS course content, FAQs, and announcements"}
        )

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        if not text or not text.strip():
            return None
        return self.embedding_model.encode(text, convert_to_numpy=True).tolist()

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict],
        ids: List[str]
    ) -> None:
        """
        Add documents to the vector store.
        
        Args:
            documents: List of text content to embed
            metadatas: List of metadata dicts (e.g., {"type": "course", "course_id": 1})
            ids: List of unique IDs for each document
        """
        if not documents or len(documents) == 0:
            return

        # Filter out empty documents
        valid_docs = []
        valid_metas = []
        valid_ids = []
        
        for doc, meta, doc_id in zip(documents, metadatas, ids):
            if doc and doc.strip():
                valid_docs.append(doc)
                valid_metas.append(meta)
                valid_ids.append(doc_id)

        if not valid_docs:
            return

        try:
            # Generate embeddings for all documents
            embeddings = self.embedding_model.encode(valid_docs, convert_to_numpy=True).tolist()
            
            # Add to collection
            self.collection.add(
                ids=valid_ids,
                embeddings=embeddings,
                documents=valid_docs,
                metadatas=valid_metas
            )
            logger.info(f"Added {len(valid_docs)} documents to vector store")
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")
            raise

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict] = None,
        user_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for similar content using semantic similarity.
        
        Args:
            query: Search query text
            n_results: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"type": "course"})
            user_id: Optional user ID to filter user-specific content
            
        Returns:
            List of dicts with keys: content, metadata, distance
        """
        if not query or not query.strip():
            return []

        try:
            # Generate query embedding
            query_embedding = self._generate_embedding(query)
            if not query_embedding:
                return []

            # Build where clause for filtering (ChromaDB requires $and for multiple conditions)
            where = None
            if filter_metadata or user_id:
                conditions = []
                if filter_metadata:
                    # Add each filter condition
                    for key, value in filter_metadata.items():
                        conditions.append({key: {"$eq": value}})
                if user_id:
                    conditions.append({"user_id": {"$eq": user_id}})
                
                # Use $and if multiple conditions, otherwise use single condition
                if len(conditions) > 1:
                    where = {"$and": conditions}
                elif len(conditions) == 1:
                    where = conditions[0]

            # Search
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where
            )

            # Format results
            formatted_results = []
            if results["ids"] and len(results["ids"][0]) > 0:
                for i in range(len(results["ids"][0])):
                    formatted_results.append({
                        "content": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if "distances" in results else None
                    })

            return formatted_results
        except Exception as e:
            logger.error(f"Error searching vector store: {e}")
            return []

    def delete_documents(self, ids: List[str]) -> None:
        """Delete documents by IDs."""
        try:
            self.collection.delete(ids=ids)
            logger.info(f"Deleted {len(ids)} documents from vector store")
        except Exception as e:
            logger.error(f"Error deleting documents: {e}")

    def update_document(self, doc_id: str, document: str, metadata: Dict) -> None:
        """Update a document in the vector store."""
        try:
            # Delete old document
            self.delete_documents([doc_id])
            # Add updated document
            self.add_documents([document], [metadata], [doc_id])
        except Exception as e:
            logger.error(f"Error updating document: {e}")

    def get_collection_stats(self) -> Dict:
        """Get statistics about the collection."""
        try:
            count = self.collection.count()
            return {
                "total_documents": count,
                "collection_name": self.collection.name
            }
        except Exception as e:
            logger.error(f"Error getting collection stats: {e}")
            return {"total_documents": 0, "collection_name": self.collection.name}

