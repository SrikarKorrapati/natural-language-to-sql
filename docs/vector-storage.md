# Persistent vector storage

Hybrid retrieval uses **Qdrant in local mode** to persist historical question embeddings and perform cosine search. SQLite remains the source of successful question/SQL pairs. The full database schema is supplied separately and is not embedded.

Install the current `requirements.txt` after updating the project. Local Qdrant runs within Python and needs no server, Docker, vector-database subscription, or additional API key. Embeddings still use the configured embedding provider and incur its usual charges. [Qdrant's local-mode documentation](https://github.com/qdrant/qdrant-client#local-mode) describes the persistent client.

## What happens during a search

1. After classification accepts the request, load up to 200 recent successful questions from SQLite for the current source database.
2. Build the search text from the current question and the last two successful questions in the current session. Embed this search text on every search.
3. Open the collection for the source database, history database, embedding endpoint, model, and vector dimension. Embed and save only candidate question texts missing from that collection. Exact duplicate texts share a vector.
4. Ask Qdrant to rank only the current candidates by cosine similarity. Stored vectors outside that set cannot appear in the results. Duplicate question records retain their individual positions in the candidate list.
5. Fuse the semantic ranking with BM25 using equal-weight RRF, `1 / (60 + rank)`, and select up to three examples. Attach their question text and SQL from SQLite to the generator prompt.

The first eligible search backfills existing history. A new successful question is indexed when it next becomes a retrieval candidate. Later searches reuse historical vectors across app restarts. Changing a historical question's text requires a new embedding. Changing the embedding provider, model, or dimension selects a separate collection; existing vectors are not mixed with the new embedding space.

Qdrant stores deterministic question identifiers and embeddings, not question text, SQL, or source-table contents. Search-query embeddings are temporary. Old collections and vectors can remain on disk even after their source questions are removed from SQLite; candidate filtering makes them ineligible for retrieval.

## Configuration and failures

| Setting | Behavior |
| --- | --- |
| `RETRIEVAL_MODE=hybrid` | Uses BM25 plus persistent Qdrant search; this is the default |
| `RETRIEVAL_MODE=keyword` | Uses BM25 alone without opening Qdrant or calling the embedding provider |
| `VECTOR_DB_PATH` | Defaults to the project's absolute `data/vectors` directory; relative overrides resolve from the project root, independent of the working directory |
| `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` | Use the embedding settings documented in the [README](../README.md#hybrid-retrieval) |

The default vector directory is ignored by Git. Empty history skips both vector storage and embedding calls. Embedding or storage errors report a brief diagnostic and fall back to BM25 for that question; later searches retry hybrid retrieval.

The app opens and closes the local client for each search and serializes access within its process. Another process holding the same directory can prevent access and trigger the BM25 fallback. Run one app process per vector directory for predictable local use. Qdrant's local mode uses exact search; this change reduces repeated embedding requests rather than establishing large-scale search performance.

## Rebuild the vector database

Stop app processes using the vector directory. Move the directory configured by `VECTOR_DB_PATH` to a separate backup location outside that path, then restart the app. The next accepted question with eligible history creates a new vector database and rebuilds missing embeddings automatically. If keeping the backup inside this repository, use another ignored location under `data/`.

SQLite history remains available throughout; no question/SQL migration is required. Rebuilding generates embedding requests again. Moving the directory preserves its contents in the backup, so it does not erase any old embeddings.

## Validation

Offline tests use an actual local Qdrant database with controlled embedding responses to check persistence, incremental indexing, collection isolation, candidate filtering, duplicate handling, and failure recovery. They make no paid API calls.

Persistent storage does not establish an SQL-accuracy gain. The published 200-question SQL benchmark starts every case with empty history, so it does not evaluate historical retrieval. Measuring retrieval quality requires questions with populated history and judged relevant examples.
