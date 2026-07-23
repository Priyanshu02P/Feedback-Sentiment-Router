import logging

from fastapi import FastAPI, HTTPException

from app.preprocessing import preprocess
from app.classifier import classify_feedback
from app.schemas import (
    PreprocessRequest,
    PreprocessResponse,
    ClassifyRequest,
    ClassifyResponse,
)

logger = logging.getLogger("feedback_service")

app = FastAPI(
    title="Feedback Processing Service",
    description=(
        "Preprocesses raw student feedback (translation, cleanup, PII "
        "redaction) and classifies it against a course-feedback taxonomy "
        "using an LLM."
    ),
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/preprocess", response_model=PreprocessResponse)
def preprocess_route(payload: PreprocessRequest):
    """Clean raw feedback text: detect + translate language, drop
    duplicate/gibberish lines, and redact PII."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="`text` must not be empty")

    detected_language, translated_text, cleaned_text, final_text = preprocess(
        text=payload.text,
        translate=payload.translate,
        remove_pii=payload.remove_pii,
        remove_duplicates=payload.remove_duplicates,
    )

    return PreprocessResponse(
        original_text=payload.text,
        detected_language=detected_language,
        translated_text=translated_text,
        cleaned_text=cleaned_text,
        pii_redacted=payload.remove_pii,
        final_text=final_text,
    )


@app.post("/classify-feedback", response_model=ClassifyResponse)
def classify_feedback_route(payload: ClassifyRequest):
    """Classify feedback text into the taxonomy (topic, sentiment, severity,
    actionability), optionally running it through /preprocess first."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="`text` must not be empty")

    text_to_classify = payload.text
    preprocessed_text = None

    if payload.preprocess:
        _, _, _, preprocessed_text = preprocess(payload.text)
        text_to_classify = preprocessed_text

    try:
        classification = classify_feedback(text_to_classify, provider=payload.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Classification failed")
        raise HTTPException(status_code=502, detail=f"Classification failed: {e}")

    return ClassifyResponse(
        input_text=payload.text,
        preprocessed_text=preprocessed_text,
        classification=classification,
    )
