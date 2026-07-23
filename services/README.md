# Feedback Pipeline Stack

Four containers, orchestrated by `docker-compose.yml`:

| Service            | Purpose                                                                 | Port (host) |
|---------------------|-------------------------------------------------------------------------|-------------|
| `postgres`           | Shared Postgres 16 instance. Hosts n8n's own `n8n` DB and a separate `feedback` DB (raw feedback, labels, clusters). | 5432 (internal only) |
| `n8n`                 | Orchestrates the workflows — calling `feedback-service` for preprocessing/classification, and `bertopic-service` for periodic topic clustering. | 5678        |
| `feedback-service`    | FastAPI service: `POST /preprocess`, `POST /classify-feedback`.        | 8001 → 8000 |
| `bertopic-service`    | FastAPI service: `POST /cluster-feedback` (the "Separate Workflow" — kept out of n8n so it can scale/move to GPU independently). | 8002 → 8000 |

```
stack/
  docker-compose.yml
  .env.example
  db/
    init/01-feedback-schema.sql   # auto-creates the `feedback` DB + tables on first boot
  feedback_service/               # preprocessing + LLM classification API
  bertopic_service/                # BERTopic clustering API
```

## Run it

```bash
cp .env.example .env
# edit .env: add OPENAI_API_KEY and/or GOOGLE_API_KEY (used by feedback-service)

docker compose up --build
```

- n8n UI: http://localhost:5678
- feedback-service docs: http://localhost:8001/docs
- bertopic-service: http://localhost:8002/health, `POST http://localhost:8002/cluster-feedback`

First run of `bertopic-service` will download the `all-MiniLM-L6-v2`
sentence-transformers model on first request (lazy-loaded), so give the
first `/cluster-feedback` call a bit of extra time.

## Database schema

`db/init/01-feedback-schema.sql` runs automatically the first time the
`postgres` volume is initialized (Postgres only executes
`/docker-entrypoint-initdb.d` scripts on an empty data directory). It creates
a `feedback` database, separate from n8n's own `n8n` database, with:

- `feedbacks (feedback_id, raw_feedback, source, created_at)`
- `feedback_labels (id, feedback_id, label, sentiment, severity, actionable, confidence, created_at)`
- `feedback_clusters (id, feedback_id, cluster_id, topic_name, probability, created_at)`

`bertopic_service/main.py` reads from `feedbacks`/`feedback_labels` (only
negative, high/critical-severity, actionable rows) and writes clusters back
into `feedback_clusters`. Your n8n workflow is expected to be what writes to
`feedbacks`/`feedback_labels` in the first place, using `feedback-service`'s
`/classify-feedback` response.

If you already have this schema managed elsewhere (e.g. a migrations tool),
just delete `db/init/` and drop the volume mount in `docker-compose.yml`.

## Resetting the stack

```bash
docker compose down -v   # -v also drops postgres_data / n8n_data volumes
```
