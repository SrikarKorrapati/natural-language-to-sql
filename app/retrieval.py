"""Equal-weight BM25 and semantic retrieval for successful past questions."""

import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

from openai import OpenAI

from app.vector_store import QdrantHistoryIndex


BM25_K1 = 1.2
BM25_B = 0.75


def tokens(text: str) -> Counter:
    """Count lowercase letter/number words, ignoring single-character tokens."""
    # Remove at most one plural s; preserve short words and endings such as "class".
    # This is still a crude stemmer (for example, "status" becomes "statu").
    return Counter(
        word[:-1] if len(word) > 2 and word.endswith("s") and not word.endswith("ss") else word
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 1
    )


def keyword_rank(query: str, texts: list[str]) -> list[int]:
    """Rank matching text indexes with BM25; exact ties retain input order."""
    query_terms = tokens(query)
    if not texts or not query_terms:
        return []
    terms = [tokens(text) for text in texts]
    lengths = [sum(doc.values()) for doc in terms]
    average_length = sum(lengths) / len(texts)
    if not average_length:
        return []
    # Count questions containing each word, rather than its total occurrences.
    frequency = Counter(word for doc in terms for word in doc)
    # Score each distinct query term once. Positive IDF keeps common terms useful.
    idf = {
        word: math.log1p((len(texts) - frequency[word] + 0.5) / (frequency[word] + 0.5))
        for word in query_terms
        if frequency[word]
    }
    scores = []
    for doc, length in zip(terms, lengths):
        normalizer = BM25_K1 * (1 - BM25_B + BM25_B * length / average_length)
        scores.append(
            sum(
                weight * doc[word] * (BM25_K1 + 1) / (doc[word] + normalizer)
                for word, weight in idf.items()
                if doc[word]
            )
        )
    ranked = sorted(range(len(texts)), key=lambda i: scores[i], reverse=True)
    return [i for i in ranked if scores[i] > 0]


class Retriever:
    """Combine BM25 with semantic search, optionally backed by a vector index."""

    def __init__(self, embed=None, vector_index: QdrantHistoryIndex | None = None):
        self.embed = embed
        self.vector_index = vector_index

    def rank(self, query: str, texts: list[str], limit: int) -> tuple[list[int], str]:
        """Return ranked text indexes and the retrieval mode actually used."""
        if type(limit) is not int or limit < 0:
            raise ValueError("limit must be a nonnegative integer")
        if not texts or limit == 0:
            return [], "none"
        keyword = keyword_rank(query, texts)
        if self.embed is None:
            return keyword[:limit], "keyword"
        try:
            semantic = self._semantic_rank(query, texts)
        except Exception as exc:
            # Recover from provider or storage failures without printing private data.
            print(
                f"Semantic retrieval unavailable ({type(exc).__name__}); using keyword-only "
                "retrieval for this question. Check EMBEDDING_BASE_URL, "
                "EMBEDDING_MODEL, EMBEDDING_API_KEY and VECTOR_DB_PATH.",
                file=sys.stderr,
            )
            return keyword[:limit], "keyword"
        fused = Counter()
        # Each search contributes equally by rank, without mixing their raw scores.
        # The offset of 60 limits how much a single top-ranked result dominates.
        for ranking in (keyword, semantic):
            for position, index in enumerate(ranking, start=1):
                fused[index] += 1 / (60 + position)
        return sorted(fused, key=lambda i: (-fused[i], i))[:limit], "hybrid"

    def _semantic_rank(self, query: str, texts: list[str]) -> list[int]:
        if self.vector_index is not None:
            return self.vector_index.rank(query, texts, self.embed)
        # Injected retrievers can still use transient vectors, useful for offline tests.
        vectors = self.embed([query, *texts])
        if len(vectors) != len(texts) + 1:
            raise ValueError("Embedding count does not match inputs")
        normalized = []
        for vector in vectors:
            norm = math.hypot(*vector)
            if not norm or not math.isfinite(norm):
                raise ValueError("Embedding must be finite and nonzero")
            if len(vector) != len(vectors[0]):
                raise ValueError("Embedding dimensions do not match")
            normalized.append([value / norm for value in vector])
        query_vector, *history_vectors = normalized
        similarities = [
            sum(a * b for a, b in zip(query_vector, vector)) for vector in history_vectors
        ]
        return sorted(range(len(texts)), key=lambda i: similarities[i], reverse=True)


def configured_retriever(*, dataset: str = "", history_path: Path | None = None) -> Retriever:
    """Create a retriever with persistent, database-scoped historical embeddings."""
    mode = os.getenv("RETRIEVAL_MODE", "hybrid").strip().lower()
    if mode not in {"hybrid", "keyword"}:
        raise ValueError("RETRIEVAL_MODE must be 'hybrid' or 'keyword'")
    if mode == "keyword":
        return Retriever()

    # Separate embedding settings override chat settings for chat-only providers.
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
    base_url = os.getenv("EMBEDDING_BASE_URL") or os.getenv(
        "OPENAI_BASE_URL", "https://api.openai.com/v1"
    )
    api_key = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")

    def embed(texts):
        with OpenAI(
            api_key=api_key, base_url=base_url, timeout=15, max_retries=0
        ) as client:
            response = client.embeddings.create(
                model=model, input=texts, encoding_format="float"
            )
        # Restore input order to keep each vector attached to its question.
        ordered = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in ordered] != list(range(len(texts))):
            raise ValueError("Embedding response indices do not match inputs")
        return [item.embedding for item in ordered]

    project_root = Path(__file__).resolve().parents[1]
    vector_path = Path(os.getenv("VECTOR_DB_PATH") or project_root / "data" / "vectors").expanduser()
    if not vector_path.is_absolute():
        vector_path = project_root / vector_path
    namespace = json.dumps(
        {
            "dataset": dataset,
            "history": str((history_path or project_root / "data" / "history.db").resolve()),
            "model": model,
            "endpoint": base_url.rstrip("/"),
        },
        sort_keys=True,
    )
    return Retriever(embed, QdrantHistoryIndex(vector_path, namespace))
