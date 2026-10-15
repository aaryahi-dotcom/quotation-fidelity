"""
Stage 3: Embedding + indexing.

Embeds chunks with sentence-transformers (all-MiniLM-L6-v2, 384 dimensions)
and writes them to a FAISS index keyed by chunk_id, matching the production
Filing Analyst Agent (RedShift SRS/SDS v9, Component 3). For each theme,
retrieves the top-k chunks by cosine similarity (k in {1, 3, 5, 10} across
this study's conditions; production default is k=5).

STATUS: NOT executed in this sandbox. sentence-transformers and faiss-cpu
could not be installed here (PyPI is unreachable in this environment -- see
build-plan notes). This module is believed correct against both libraries'
documented APIs but is unverified; run embed_index.py's __main__ block
wherever the packages are actually installed and fix anything that surfaces.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

from chunk import Chunk

MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_DIM = 384


@dataclass
class ChunkIndex:
    """A FAISS index plus the chunk metadata needed to resolve a search hit
    back to a Chunk object (FAISS itself only knows integer row ids)."""
    index: "object"            # faiss.Index, typed loosely to avoid a hard
                                # import-time dependency for callers that
                                # only need the dataclass shape (e.g. tests).
    chunks_by_row: list[Chunk]
    model: object


def build_index(chunks: list[Chunk]) -> ChunkIndex:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode([c.text for c in chunks], normalize_embeddings=True,
                               show_progress_bar=False)
    embeddings = np.asarray(embeddings, dtype="float32")

    # Cosine similarity via inner product on L2-normalised vectors.
    index = faiss.IndexFlatIP(EMBED_DIM)
    index.add(embeddings)

    return ChunkIndex(index=index, chunks_by_row=list(chunks), model=model)


def retrieve(chunk_index: ChunkIndex, query: str, k: int) -> list[Chunk]:
    import numpy as np

    model = chunk_index.model
    query_vec = model.encode([query], normalize_embeddings=True,
                              show_progress_bar=False)
    query_vec = np.asarray(query_vec, dtype="float32")

    scores, rows = chunk_index.index.search(query_vec, k)
    return [chunk_index.chunks_by_row[i] for i in rows[0] if i != -1]


def save_index(chunk_index: ChunkIndex, path: str) -> None:
    import faiss
    faiss.write_index(chunk_index.index, f"{path}.faiss")
    with open(f"{path}.chunks.pkl", "wb") as f:
        pickle.dump(chunk_index.chunks_by_row, f)


def load_index(path: str) -> ChunkIndex:
    import faiss
    index = faiss.read_index(f"{path}.faiss")
    with open(f"{path}.chunks.pkl", "rb") as f:
        chunks_by_row = pickle.load(f)
    return ChunkIndex(index=index, chunks_by_row=chunks_by_row)


if __name__ == "__main__":
    from chunk import Chunk

    sample_chunks = [
        Chunk("T1", "TEST", "2020", 1, 1, None,
              "The company reported strong revenue growth driven by exports.", 10),
        Chunk("T2", "TEST", "2020", 2, 2, None,
              "Auditors noted material uncertainty related to going concern.", 9),
    ]
    idx = build_index(sample_chunks)
    hits = retrieve(idx, "going concern doubt", k=1)
    print("Top hit:", hits[0].chunk_id, hits[0].text)
    assert hits[0].chunk_id == "T2", "retrieval sanity check failed"
    print("Self-test passed (run where faiss + sentence-transformers are installed).")
