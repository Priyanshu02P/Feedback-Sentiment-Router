"""
Pydantic schemas.

The classification taxonomy / labels mirror what was prototyped in
FeedbackClassifier.ipynb.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Preprocessing
# --------------------------------------------------------------------------

class PreprocessRequest(BaseModel):
    text: str = Field(..., description="Raw feedback text to clean")
    translate: bool = Field(
        True, description="Detect non-English text and translate it to English"
    )
    remove_pii: bool = Field(True, description="Redact PII (email, phone, etc.)")
    remove_duplicates: bool = Field(
        True, description="Collapse consecutive duplicate/gibberish lines"
    )


class PreprocessResponse(BaseModel):
    original_text: str
    detected_language: Optional[str] = None
    translated_text: Optional[str] = None
    cleaned_text: str
    pii_redacted: bool
    final_text: str = Field(
        ..., description="Fully preprocessed text, ready for classification"
    )


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

class Sentiment(str, Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"
    mixed = "mixed"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TaxonomyLabel(str, Enum):
    TUTOR_DELIVERY = "Tutor|Delivery"
    TUTOR_COMMUNICATION = "Tutor|Communication"
    TUTOR_KNOWLEDGE = "Tutor|Knowledge"
    TUTOR_PACE = "Tutor|Pace"

    CONTENT_DIFFICULTY = "Content|Difficulty"
    CONTENT_RELEVANCE = "Content|Relevance"
    CONTENT_CLARITY = "Content|Clarity"
    CONTENT_PACE = "Content|Pace"

    ASSESSMENT_FAIRNESS = "Assessment|Fairness"
    ASSESSMENT_DIFFICULTY = "Assessment|Difficulty"
    ASSESSMENT_ALIGNMENT = "Assessment|Alignment"

    ADMIN_SCHEDULING = "Administration|Scheduling"
    ADMIN_COMMUNICATION = "Administration|Communication"

    TECH_CONTENT = "Tech|Content"
    TECH_ASSESSMENT = "Tech|Assessment"
    TECH_PLATFORM = "Tech|Platform"
    TECH_MEDIA = "Tech|Media"
    TECH_UX = "Tech|UX"
    TECH_INFRA = "Tech|Infra"

    UNKNOWN = "Unknown|Unknown"


class FeedbackLabel(BaseModel):
    label: TaxonomyLabel
    sentiment: Sentiment
    severity: Severity
    confidence: float = Field(ge=0, le=1)


class FeedbackClassification(BaseModel):
    actionable: bool = Field(
        ..., description="Whether the feedback requires action or investigation"
    )
    summary: str = Field(..., description="Short 1-2 sentence summary of the feedback")
    labels: List[FeedbackLabel] = Field(
        default_factory=list, description="One or more classified topics"
    )


class ClassifyRequest(BaseModel):
    text: str = Field(..., description="Feedback text to classify")
    provider: str = Field(
        "openai", description="LLM provider to use: 'openai' or 'gemini'"
    )
    preprocess: bool = Field(
        False,
        description="If true, runs the /preprocess pipeline on the text first",
    )


class ClassifyResponse(BaseModel):
    input_text: str
    preprocessed_text: Optional[str] = None
    classification: FeedbackClassification
