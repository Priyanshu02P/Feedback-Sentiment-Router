"""
BERTopic clustering service — the "Separate Workflow" in the architecture diagram.

n8n Workflow 2 (2_bertopic_clustering_trigger.json) calls POST /cluster-feedback
on this service. It stays out of n8n entirely so it can be scaled or moved to
GPU hardware independently.

Run:
    pip install fastapi uvicorn psycopg2-binary sentence-transformers bertopic hdbscan umap-learn
    uvicorn main:app --host 0.0.0.0 --port 8000

Env vars:
    DATABASE_URL   postgres connection string, e.g. postgresql://user:pass@host:5432/feedback
"""
import os
import uuid
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from bertopic import BERTopic
from hdbscan import HDBSCAN
from umap import UMAP

app = FastAPI(title="Feedback BERTopic Service")

DATABASE_URL = os.environ["DATABASE_URL"]
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


class ClusterRequest(BaseModel):
    days: int = 30


class ClusterResponse(BaseModel):
    status: str
    clusters_found: int
    feedbacks_clustered: int


def fetch_candidate_feedback(conn, days: int):
    """
    Only cluster negative, high-severity, actionable feedback -- this is what
    keeps topic quality high per the design doc (praise and neutral noise excluded).
    """
    query = """
        SELECT DISTINCT f.feedback_id, f.raw_feedback
        FROM feedbacks f
        JOIN feedback_labels fl ON fl.feedback_id = f.feedback_id
        WHERE fl.sentiment = 'negative'
          AND fl.severity IN ('high', 'critical')
          AND fl.actionable = TRUE
          AND fl.created_at >= NOW() - INTERVAL '%s days'
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (days,))
        return cur.fetchall()


def run_bertopic(docs: list[str]):
    embedder = get_embedder()
    embeddings = embedder.encode(docs, show_progress_bar=False)

    umap_model = UMAP(n_neighbors=15, n_components=5, min_dist=0.0, metric="cosine", random_state=42)
    hdbscan_model = HDBSCAN(min_cluster_size=10, metric="euclidean", cluster_selection_method="eom")

    topic_model = BERTopic(
        embedding_model=embedder,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        calculate_probabilities=True,
    )
    topics, probs = topic_model.fit_transform(docs, embeddings)
    return topic_model, topics, probs


def store_clusters(conn, feedback_ids, topics, probs, topic_model):
    rows = []
    for feedback_id, topic_id, prob in zip(feedback_ids, topics, probs):
        if topic_id == -1:
            continue  # -1 = HDBSCAN outlier / noise, not a real cluster
        topic_words = topic_model.get_topic(topic_id)
        topic_name = ", ".join(word for word, _ in topic_words[:4]) if topic_words else f"topic_{topic_id}"
        # probs can be a 2D array (per-topic probability) depending on BERTopic version
        probability = float(prob) if not hasattr(prob, "__len__") else float(max(prob))
        rows.append((str(uuid.uuid4()), feedback_id, str(topic_id), topic_name, probability))

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO feedback_clusters (id, feedback_id, cluster_id, topic_name, probability, created_at)
            VALUES %s
            """,
            [(r[0], r[1], r[2], r[3], r[4], datetime.utcnow()) for r in rows],
        )
    conn.commit()
    return len(rows)


@app.post("/cluster-feedback", response_model=ClusterResponse)
def cluster_feedback(req: ClusterRequest):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        candidates = fetch_candidate_feedback(conn, req.days)
        if len(candidates) < 10:
            # BERTopic/HDBSCAN need a reasonable minimum sample size to form clusters
            return ClusterResponse(status="ok", clusters_found=0, feedbacks_clustered=0)

        feedback_ids = [c["feedback_id"] for c in candidates]
        docs = [c["raw_feedback"] for c in candidates]

        topic_model, topics, probs = run_bertopic(docs)
        stored = store_clusters(conn, feedback_ids, topics, probs, topic_model)
        n_clusters = len(set(t for t in topics if t != -1))

        return ClusterResponse(status="ok", clusters_found=n_clusters, feedbacks_clustered=stored)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}
