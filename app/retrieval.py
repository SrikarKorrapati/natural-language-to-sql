"""Equal-weight keyword and semantic retrieval for successful past questions."""

import math
import os
import re
import sys
from collections import Counter

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
    """Combine keyword search with fresh embeddings for each history search."""

    def __init__(self, embed=None):
        self.embed = embed

    def rank(self, query: str, texts: list[str], limit: int) -> tuple[list[int], str]:
        """Return ranked text indexes and the retrieval mode actually used."""
        if not texts:
            return [], "none"
        keyword = keyword_rank(query, texts)
        if self.embed is None:
            return keyword[:limit], "keyword"
        try:
            # Embed the search and all candidates; keep vectors local to this call.
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
                # Unit-length vectors make their dot product equal cosine similarity.
                normalized.append([value / norm for value in vector])
        except Exception as exc:
            # Recover from provider failures without printing request data.
            print(
                f"Embeddings unavailable ({type(exc).__name__}); using keyword-only "
                "retrieval for this question. Check EMBEDDING_BASE_URL, "
                "EMBEDDING_MODEL and EMBEDDING_API_KEY.",
                file=sys.stderr,
            )
            return keyword[:limit], "keyword"
        query_vector, *history_vectors = normalized
        similarities = [
            sum(a * b for a, b in zip(query_vector, vector)) for vector in history_vectors
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
        return sorted(fused, key=lambda i: (-fused[i], i))[:limit], "hybrid"


def configured_retriever() -> Retriever:
    """Create a retriever using the current environment settings."""
    if os.getenv("RETRIEVAL_MODE", "hybrid") != "hybrid":
        return Retriever()

    # Separate embedding settings override chat settings for chat-only providers.
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
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

    return Retriever(embed)
