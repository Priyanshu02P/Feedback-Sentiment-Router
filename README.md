# Feedback Classification

An end-to-end pipeline that turns raw course feedback (text, any language)
into structured, actionable data: preprocessed + PII-redacted text, an
LLM classification against a fixed taxonomy (topic, sentiment, severity,
actionability), topic clusters for recurring negative issues, KPIs, alerts,
and testimonial candidates — all orchestrated by n8n.

```
Raw feedback → preprocess → LLM classify → store labels
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
        BERTopic clustering          KPI generation /            Positive feedback
     (negative, high-severity,        alert engine /              → testimonials
        actionable feedback)         trend detection
```

## Repo layout

```
services/                  Dockerized services + the compose stack
  feedback_service/          FastAPI: POST /preprocess, POST /classify-feedback
  bertopic_service/          FastAPI: POST /cluster-feedback (topic clustering)
  db/init/                    Postgres bootstrap SQL for the `feedback` DB
  README.md                   Stack-level docs (services, ports, run/reset)
docker-compose.yml          Orchestrates postgres + n8n + both FastAPI services
workflows/                  n8n workflow exports (import into n8n) + schema.sql
prompts/                    System/user prompts + few-shot examples for the
                              classifier LLM (the taxonomy lives here)
notebooks/                  Original exploration notebooks the services were
                              built from
docs/                       Design notes (topic taxonomy, rating-based trend
                              analysis)
.env_example                Template for OPENAI_API_KEY / GOOGLE_API_KEY
```

## Quick start

```bash
cp .env_example .env
# edit .env: set OPENAI_API_KEY and/or GOOGLE_API_KEY

docker compose up --build
```

This starts four containers:

| Service            | Purpose                                                                                   | Port           |
|---------------------|---------------------------------------------------------------------------------------------|----------------|
| `postgres`            | Postgres 16 — hosts n8n's own DB plus a separate `feedback` DB (raw feedback, labels, clusters). | 5432 (internal) |
| `n8n`                  | Orchestrates the workflows below.                                                            | 5678           |
| `feedback-service`     | FastAPI: language detect/translate, dedup/gibberish removal, PII redaction, LLM classification. | 8001 → 8000    |
| `bertopic-service`     | FastAPI: clusters negative/high-severity/actionable feedback into topics via BERTopic.       | 8002 → 8000    |

- n8n UI: http://localhost:5678
- feedback-service docs: http://localhost:8001/docs
- bertopic-service health: http://localhost:8002/health

Then, in the n8n UI, import the workflows from `workflows/` (see below) and
activate them.

See `services/README.md` for the full stack breakdown (schema, resetting
volumes, standalone Docker run) and `services/feedback_service/README.md`
for the classification API itself (routes, request/response examples,
setup without Docker).

## n8n workflows

Import these into n8n (`workflows/*.json`). Each includes a manual-trigger
"test"/"mock" path so it can be exercised without waiting for its schedule.

| # | Workflow | Trigger | What it does |
|---|----------|---------|---------------|
| 1 | Feedback Processing Pipeline | every 5 min | Pulls unprocessed feedback, preprocesses + strips PII, calls `feedback-service` for LLM classification, and either writes labels (confidence ≥ 0.70) or routes to a review queue. |
| 2 | BERTopic Clustering Trigger | daily 02:00 | Calls `bertopic-service` to cluster recent negative/high-severity/actionable feedback into topics; alerts Slack on failure. |
| 3 | KPI Generation | nightly 01:00 | Computes KPIs from labeled feedback, applies thresholds, snapshots them. |
| 4 | Alert Engine | hourly | Finds KPIs breaching thresholds and notifies Slack + email. |
| 5 | Trend Detection | daily 03:00 | Compares week-over-week cluster sizes and alerts course leads to emerging issues. |
| 6 | Positive Feedback → Testimonials | manual | Pulls new positive feedback and stages it as testimonial candidates. |

`workflows/schema.sql` is a standalone copy of the schema referenced by the
workflows (feedbacks, feedback_classifications, feedback_labels,
review_queue, feedback_clusters). The version that actually runs when you
`docker compose up` is `services/db/init/01-feedback-schema.sql`, which
auto-creates the `feedback` database on first Postgres boot — the two have
diverged slightly (extra `course_id`/`review_queue` columns in the workflow
copy), so treat `services/db/init/` as the source of truth for the running
stack and reconcile `workflows/schema.sql` before relying on it.

## Classification taxonomy

The classifier (`prompts/system_prompt.txt`, used by
`services/feedback_service/app/classifier.py`) labels each piece of feedback
with one or more `Category → Sub-category` pairs, plus sentiment, severity,
and an actionability flag:

- **Tutor**: Delivery, Communication, Knowledge, Pace
- **Content**: Difficulty, Relevance, Clarity, Pace
- **Assessment**: Fairness, Difficulty, Alignment
- **Administration**: Scheduling, Communication
- **Tech**: Content, Assessment, Platform, Media, UX, Infra
- **Unknown**: fallback when nothing else fits

Sentiment: `Positive / Negative / Neutral / Mixed`. Severity:
`Critical / High / Medium / Low`, scored by business impact (e.g. Critical =
blocks learning or assessment). Feedback is marked non-actionable when it's
pure praise, pure preference, too vague, or unrelated to the course. See
`prompts/examples.txt` for the few-shot examples and `docs/Feedback
Topics.pdf` for the design notes behind the taxonomy (built from the
[Coursera course reviews dataset](https://www.kaggle.com/datasets/imuhammad/course-reviews-on-coursera)).

## Notebooks

The FastAPI services are the productionized version of these exploration
notebooks:

- `Preprocessing.ipynb` → `services/feedback_service/app/preprocessing.py`
- `FeedbackClassifier.ipynb` → `services/feedback_service/app/classifier.py`
- `FeedbackRatingTopics.ipynb` — rating-based topic/trend analysis behind
  `docs/Feedback Topics.pdf`

See `services/feedback_service/README.md` → "Notes on what changed vs. the
notebooks" for specifics (e.g. lightweight translation instead of the
notebook's `nllb-200` model, env-var config instead of Colab userdata).

## Resetting the stack

```bash
docker compose down -v   # -v also drops postgres_data / n8n_data volumes
```