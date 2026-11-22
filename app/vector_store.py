"""Persistent local Qdrant index for historical question embeddings."""

import hashlib
import json
import math
import threading
from contextlib import closing
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models


# A local Qdrant folder has one exclusive client. Do not hold that client between
# searches; LangGraph can execute different questions on different worker threads.
_LOCAL_LOCK = threading.Lock()


def _normalize_vectors(vectors, expected_count: int, dimension: int | None = None):
    """Reject malformed responses before storing or searching with their vectors."""
    if len(vectors) != expected_count:
        raise ValueError("Embedding count does not match inputs")
    normalized = []
    for vector in vectors:
        if dimension is None:
            dimension = len(vector)
        if not dimension or len(vector) != dimension:
            raise ValueError("Embedding dimensions do not match")
        norm = math.hypot(*vector)
        if not norm or not math.isfinite(norm):
            raise ValueError("Embedding must be finite and nonzero")
        normalized.append([value / norm for value in vector])
    return normalized


class QdrantHistoryIndex:
    """Embed missing questions and search only the current history candidates."""

    def __init__(self, path: Path, namespace: str):
        # Construction must not create storage for rejected requests or empty history.
        self.path = Path(path).expanduser()
        self.namespace = namespace

    def _collection_name(self, dimension: int) -> str:
        identity = json.dumps([1, self.namespace, dimension], ensure_ascii=True)
        return "history_" + hashlib.sha256(identity.encode()).hexdigest()

    def rank(self, query: str, texts: list[str], embed) -> list[int]:
        if not texts:
            return []
        # The query is always fresh. Its dimension selects a compatible collection.
        query_vector = _normalize_vectors(embed([query]), 1)[0]
        dimension = len(query_vector)
        collection = self._collection_name(dimension)
        unique_texts = list(dict.fromkeys(texts))
        ids = {text: str(uuid5(NAMESPACE_URL, text)) for text in unique_texts}
        wanted_ids = list(ids.values())

        with _LOCAL_LOCK, closing(QdrantClient(path=str(self.path))) as client:
            if not client.collection_exists(collection):
                client.create_collection(
                    collection_name=collection,
                    vectors_config=models.VectorParams(
                        size=dimension, distance=models.Distance.COSINE
                    ),
                )
            stored = client.retrieve(
                collection_name=collection,
                ids=wanted_ids,
                with_payload=False,
                with_vectors=False,
            )
            existing = {str(point.id) for point in stored}
            missing = [text for text in unique_texts if ids[text] not in existing]
            if missing:
                vectors = _normalize_vectors(embed(missing), len(missing), dimension)
                client.upsert(
                    collection_name=collection,
                    points=[
                        models.PointStruct(id=ids[text], vector=vector)
                        for text, vector in zip(missing, vectors)
                    ],
                    wait=True,
                )
            matches = client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=models.Filter(
                    must=[models.HasIdCondition(has_id=wanted_ids)]
                ),
                limit=len(wanted_ids),
                with_payload=False,
                with_vectors=False,
            ).points

        scores = {str(point.id): point.score for point in matches}
        if len(matches) != len(wanted_ids) or set(scores) != set(wanted_ids):
            raise ValueError("Vector search did not return the current candidates")
        if not all(math.isfinite(score) for score in scores.values()):
            raise ValueError("Vector search returned a nonfinite score")
        # Preserve duplicate question records and deterministic ties in caller order.
        return sorted(range(len(texts)), key=lambda i: (-scores[ids[texts[i]]], i))
