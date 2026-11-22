"""Offline integration tests using actual persistent local Qdrant collections."""

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from qdrant_client import QdrantClient

from app.vector_store import QdrantHistoryIndex


def recording_embed(vectors, calls):
    def embed(texts):
        calls.append(list(texts))
        return [vectors[text] for text in texts]

    return embed


def test_vector_store_is_lazy_and_empty_history_needs_no_embeddings(tmp_path):
    path = tmp_path / "vectors"
    index = QdrantHistoryIndex(path, "database-a")
    assert not path.exists()
    assert index.rank("buyers", [], lambda *_: pytest.fail("No history")) == []
    assert not path.exists()


def test_vectors_persist_and_new_instances_only_embed_the_query(tmp_path):
    calls = []
    embed = recording_embed(
        {"buyers": [1, 0], "customers": [1, 1], "inventory": [0, 1]}, calls
    )
    path = tmp_path / "vectors"
    documents = ["customers", "inventory"]
    assert QdrantHistoryIndex(path, "database-a").rank("buyers", documents, embed) == [0, 1]
    assert calls == [["buyers"], documents]
    assert QdrantHistoryIndex(path, "database-a").rank("buyers", documents, embed) == [0, 1]
    assert calls == [["buyers"], documents, ["buyers"]]

    # The client was released, and only vectors/IDs are persisted, not question/SQL payloads.
    with closing(QdrantClient(path=str(path))) as client:
        collections = client.get_collections().collections
        assert len(collections) == 1
        points, _ = client.scroll(collections[0].name, with_vectors=True)
        assert len(points) == 2
        assert all(not point.payload and len(point.vector) == 2 for point in points)


def test_only_new_or_edited_questions_are_embedded_and_old_candidates_excluded(tmp_path):
    calls = []
    embed = recording_embed(
        {
            "buyers": [1, 0],
            "customers": [1, 0],
            "inventory": [0, 1],
            "inventory updated": [-1, 0],
        },
        calls,
    )
    index = QdrantHistoryIndex(tmp_path / "vectors", "database-a")
    assert index.rank("buyers", ["customers", "inventory"], embed) == [0, 1]
    # The previously indexed, closest customer question is not a current candidate.
    assert index.rank("buyers", ["inventory updated", "inventory"], embed) == [1, 0]
    assert calls == [
        ["buyers"], ["customers", "inventory"], ["buyers"], ["inventory updated"]
    ]
    assert index.rank("buyers", ["inventory updated"], embed) == [0]
    assert calls[-1] == ["buyers"]


def test_duplicate_questions_and_score_ties_preserve_candidate_order(tmp_path):
    calls = []
    embed = recording_embed(
        {"buyers": [1, 0], "customers": [1, 0], "clients": [1, 0], "stock": [-1, 0]},
        calls,
    )
    index = QdrantHistoryIndex(tmp_path / "vectors", "database-a")
    documents = ["stock", "customers", "clients", "customers"]
    assert index.rank("buyers", documents, embed) == [1, 2, 3, 0]
    assert calls == [["buyers"], ["stock", "customers", "clients"]]
    assert index.rank("buyers", ["clients", "customers", "clients"], embed) == [0, 1, 2]
    assert calls[-1] == ["buyers"]


def test_namespaces_keep_databases_and_embedding_configurations_separate(tmp_path):
    calls = []
    embed = recording_embed({"buyers": [1, 0], "customers": [1, 0]}, calls)
    path = tmp_path / "vectors"
    for namespace in ("database-a/model-a", "database-b/model-a", "database-a/model-b"):
        assert QdrantHistoryIndex(path, namespace).rank("buyers", ["customers"], embed) == [0]
    assert calls == [["buyers"], ["customers"]] * 3
    assert QdrantHistoryIndex(path, "database-a/model-a").rank("buyers", ["customers"], embed) == [0]
    assert calls[-1] == ["buyers"]
    assert len(calls) == 7
    with closing(QdrantClient(path=str(path))) as client:
        assert len(client.get_collections().collections) == 3


def test_dimension_changes_select_separate_collections_and_reuse_compatible_vectors(tmp_path):
    calls = []
    path = tmp_path / "vectors"
    index = QdrantHistoryIndex(path, "database-a")
    vectors = {"buyers": [1, 0], "customers": [1, 1]}
    embed = recording_embed(vectors, calls)
    assert index.rank("buyers", ["customers"], embed) == [0]
    vectors.update({"buyers": [1, 0, 0], "customers": [1, 1, 0]})
    assert index.rank("buyers", ["customers"], embed) == [0]
    vectors.update({"buyers": [1, 0], "customers": [1, 1]})
    assert index.rank("buyers", ["customers"], embed) == [0]
    assert calls == [["buyers"], ["customers"], ["buyers"], ["customers"], ["buyers"]]
    with closing(QdrantClient(path=str(path))) as client:
        assert len(client.get_collections().collections) == 2


@pytest.mark.parametrize(
    "vectors",
    [[], [[1, 0], [1, 0]], [[]], [[0, 0]], [[float("nan"), 1]], [[float("inf"), 1]]],
)
def test_invalid_query_embeddings_do_not_create_storage(tmp_path, vectors):
    path = tmp_path / "vectors"
    with pytest.raises(ValueError, match="Embedding"):
        QdrantHistoryIndex(path, "database-a").rank("buyers", ["customers"], lambda *_: vectors)
    assert not path.exists()


@pytest.mark.parametrize(
    "vectors",
    [[], [[1, 0]], [[1, 0], [1, 0, 0]], [[1, 0], [0, 0]], [[1, 0], [float("nan"), 1]]],
)
def test_bad_history_batch_is_not_partly_persisted_and_releases_client(tmp_path, vectors):
    path = tmp_path / "vectors"
    index = QdrantHistoryIndex(path, "database-a")
    responses = iter([[[1, 0]], vectors])
    with pytest.raises(ValueError, match="Embedding"):
        index.rank("buyers", ["customers", "inventory"], lambda *_: next(responses))
    with closing(QdrantClient(path=str(path))) as client:
        collection = client.get_collections().collections[0].name
        assert client.count(collection).count == 0
    calls = []
    embed = recording_embed(
        {"buyers": [1, 0], "customers": [1, 0], "inventory": [0, 1]}, calls
    )
    assert index.rank("buyers", ["customers", "inventory"], embed) == [0, 1]
    assert calls == [["buyers"], ["customers", "inventory"]]


def test_provider_failure_releases_client_and_can_recover(tmp_path):
    path = tmp_path / "vectors"
    index = QdrantHistoryIndex(path, "database-a")

    def unavailable(texts):
        if texts == ["buyers"]:
            return [[1, 0]]
        raise RuntimeError("Provider unavailable")

    with pytest.raises(RuntimeError, match="Provider unavailable"):
        index.rank("buyers", ["customers"], unavailable)
    with closing(QdrantClient(path=str(path))) as client:
        assert len(client.get_collections().collections) == 1
    assert index.rank("buyers", ["customers"], lambda texts: [[1, 0] for _ in texts]) == [0]


def test_busy_local_store_propagates_error_and_recovers_when_released(tmp_path):
    path = tmp_path / "vectors"
    index = QdrantHistoryIndex(path, "database-a")
    embed = lambda texts: [[1, 0] for _ in texts]
    with closing(QdrantClient(path=str(path))):
        with pytest.raises(RuntimeError, match="already accessed"):
            index.rank("buyers", ["customers"], embed)
    assert index.rank("buyers", ["customers"], embed) == [0]


def test_worker_threads_share_storage_without_duplicate_indexing_or_open_clients(tmp_path):
    path = tmp_path / "vectors"
    ready = Barrier(2)
    calls = []

    def embed(texts):
        calls.append(list(texts))
        if texts == ["buyers"]:
            ready.wait(timeout=5)
        return [[1, 0] for _ in texts]

    def rank(_):
        return QdrantHistoryIndex(path, "database-a").rank("buyers", ["customers"], embed)

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert list(workers.map(rank, range(2))) == [[0], [0]]
    assert calls.count(["buyers"]) == 2
    assert calls.count(["customers"]) == 1
    with closing(QdrantClient(path=str(path))) as client:
        collection = client.get_collections().collections[0].name
        assert client.count(collection).count == 1
