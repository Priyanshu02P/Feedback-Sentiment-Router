# Feedback Processing Service

A FastAPI service built from `Preprocessing.ipynb` and `FeedbackClassifier.ipynb`.

## Routes

| Method | Path                | Description                                                        |
|--------|----------------------|----------------------------------------------------------------------|
| GET    | `/health`             | Liveness check                                                      |
| POST   | `/preprocess`          | Language-detect + translate, drop duplicate/gibberish lines, redact PII |
| POST   | `/classify-feedback`   | Classify feedback against the course-feedback taxonomy via an LLM   |

Interactive docs are available at `/docs` once the server is running.

## Project layout

```
app/
  main.py           FastAPI app + route handlers
  schemas.py        Pydantic request/response models & taxonomy enums
  preprocessing.py  Language detection/translation, dedup/gibberish removal, PII redaction
  classifier.py     LangChain structured-output classification (OpenAI / Gemini)
  config.py         Settings (reads OPENAI_API_KEY / GOOGLE_API_KEY from env or .env)
requirements.txt
.env.example
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and add your OPENAI_API_KEY and/or GOOGLE_API_KEY
```

Optional — enable spaCy-based NER PII redaction (in addition to the regex
patterns, which are always on) on top of person/org/location names:

```bash
pip install spacy
python -m spacy download en_core_web_sm
```

If this model isn't installed, `/preprocess` still works fine and just skips
the NER step, relying on the regex patterns.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

## Example requests

### `POST /preprocess`

```bash
curl -X POST http://localhost:8000/preprocess \
  -H "Content-Type: application/json" \
  -d '{
        "text": "good\ngood\ngood\nsfnenvj\nMy email is john.doe@gmail.com, phone 9876543210"
      }'
```

```json
{
  "original_text": "...",
  "detected_language": "en",
  "translated_text": null,
  "cleaned_text": "good\nMy email is john.doe@gmail.com, phone 9876543210",
  "pii_redacted": true,
  "final_text": "good\nMy email is [EMAIL], phone [PHONE]"
}
```

### `POST /classify-feedback`

```bash
curl -X POST http://localhost:8000/classify-feedback \
  -H "Content-Type: application/json" \
  -d '{
        "text": "The tutor explains well but the auto grader keeps giving zero for correct answers.",
        "provider": "openai",
        "preprocess": true
      }'
```

```json
{
  "input_text": "...",
  "preprocessed_text": "...",
  "classification": {
    "actionable": true,
    "summary": "Auto grader incorrectly scores correct answers.",
    "labels": [
      { "label": "Tutor|Delivery", "sentiment": "positive", "severity": "low", "confidence": 0.9 },
      { "label": "Tech|Assessment", "sentiment": "negative", "severity": "high", "confidence": 0.95 }
    ]
  }
}
```

Set `"provider": "gemini"` to use `GOOGLE_API_KEY` / Gemini instead of OpenAI.

## Running as part of the full stack

This service is one of three containers in the top-level `docker-compose.yml`
(alongside `n8n`/`postgres` and `bertopic_service`, the separate BERTopic
clustering API). See the root `README.md` for the full picture. To run just
this service standalone with Docker:

```bash
docker build -t feedback-service .
docker run --rm -p 8000:8000 --env-file .env feedback-service
```

## Notes on what changed vs. the notebooks

- Translation uses the lightweight `langdetect` + `deep_translator` (Google
  Translate) approach from the notebook rather than the heavyweight
  `facebook/nllb-200-distilled-600M` transformers pipeline, to keep the
  service fast to start and light to deploy. Swap in
  `transformers`/`presidio` in `app/preprocessing.py` if you'd rather use
  those instead.
- `google.colab.userdata` is replaced with environment variables /
  `pydantic-settings` (`app/config.py`) so the service runs outside Colab.
- Enum values in the classification schema are lowercased (`"positive"`,
  `"low"`, etc.) and `label` uses the `Category|Subcategory` taxonomy enum
  directly, for a stricter, self-documenting schema.
