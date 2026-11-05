"""Equal-weight keyword and semantic retrieval for successful past questions."""

import math
import os
import re
import sys
from collections import Counter
from functools import lru_cache

from openai import OpenAI


def tokens(text: str) -> Counter:
    """Count lowercase letter/number words, ignoring single-character tokens."""
    # Stripping final s characters roughly matches plurals, but also changes "status".
    return Counter(
        word.rstrip("s")
        for word in re.findall(r"[a-z0-9]+", text.lower())
        if len(word) > 1
    )


def keyword_rank(query: str, texts: list[str]) -> list[int]:
    """Return matching text indexes, ranked by IDF-weighted word overlap."""
    terms = [tokens(text) for text in texts]
    query_terms = tokens(query)
    # Count questions containing each word, rather than its total occurrences.
    frequency = Counter(word for doc in terms for word in doc)
    # Shared occurrences earn more weight when the word appears in fewer questions.
    scores = [
        sum(
            min(count, doc[word])
            * (1 + math.log((len(texts) + 1) / (frequency[word] + 1)))
            for word, count in query_terms.items()
        )
        for doc in terms
    ]
    ranked = sorted(range(len(texts)), key=lambda i: scores[i], reverse=True)
    return [i for i in ranked if scores[i] > 0]


class Retriever:
    """Combine keyword search with optional embeddings cached for this process."""

    def __init__(self, embed=None):
        self.embed = embed
        self.cache = {}

    def prepare(self, texts: list[str]) -> bool:
        """Cache new embeddings; return whether semantic search is available."""
        if self.embed is None:
            return False
        # Repeated questions and previously cached texts need no new provider request.
        missing = list(dict.fromkeys(text for text in texts if text not in self.cache))
        try:
            if missing:
                vectors = self.embed(missing)
                normalized = {}
                dimensions = (
                    len(next(iter(self.cache.values()))) if self.cache else None
                )
                for text, vector in zip(missing, vectors, strict=True):
                    norm = math.hypot(*vector)
                    if not norm or not math.isfinite(norm):
                        raise ValueError("Embedding must be finite and nonzero")
                    if dimensions is not None and len(vector) != dimensions:
                        raise ValueError("Embedding dimensions changed")
                    dimensions = len(vector)
                    # Unit-length vectors make their dot product equal cosine similarity.
                    normalized[text] = [value / norm for value in vector]
                # Keep the cache unchanged if any vector in this batch is invalid.
                self.cache.update(normalized)
        except Exception as exc:
            # Recover from provider failures without printing request data.
            print(
                f"Embeddings unavailable ({type(exc).__name__}); using keyword-only "
                "retrieval for this process. Check EMBEDDING_BASE_URL, "
                "EMBEDDING_MODEL and EMBEDDING_API_KEY, then restart to retry.",
                file=sys.stderr,
            )
            # Avoid repeating a failed embedding request on every later question.
            self.embed = None
            return False
        return True

    def rank(self, query, texts, limit):
        """Give keyword and semantic ranks equal weight with reciprocal rank fusion."""
        keyword = keyword_rank(query, texts)
        if self.embed is None or not texts:
            return keyword[:limit]
        query_vector = self.cache[query]
        similarities = [
            sum(a * b for a, b in zip(query_vector, self.cache[text])) for text in texts
        ]
        semantic = sorted(
            range(len(texts)), key=lambda i: similarities[i], reverse=True
        )
        fused = Counter()
        # Each search contributes equally by rank, without mixing their raw scores.
        # The offset of 60 limits how much a single top-ranked result dominates.
        for ranking in (keyword, semantic):
            for position, index in enumerate(ranking, start=1):
                fused[index] += 1 / (60 + position)
        return sorted(fused, key=lambda i: (-fused[i], i))[:limit]


@lru_cache(maxsize=8)
def _configured_retriever(mode, model, base_url, api_key):
    """Reuse a retriever and its text cache for each provider configuration."""

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

    return Retriever(embed if mode == "hybrid" else None)


def configured_retriever() -> Retriever:
    """Share cached vectors between agents using the same provider configuration."""
    # Separate embedding settings override chat settings for chat-only providers.
    return _configured_retriever(
        os.getenv("RETRIEVAL_MODE", "hybrid"),
        os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        os.getenv("EMBEDDING_BASE_URL")
        or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY"),
    )
