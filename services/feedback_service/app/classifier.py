"""
Feedback classification pipeline, ported from FeedbackClassifier.ipynb.

Uses LangChain structured output against the FeedbackClassification schema.
Provider (OpenAI / Gemini) and API keys are read from environment variables
via app/config.py instead of google.colab.userdata.
"""
from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate

from app.config import get_settings
from app.schemas import FeedbackClassification

SYSTEM_PROMPT = """
You are a course feedback classification engine.

Your task is to analyze student feedback and produce structured JSON.

The objective is to identify actionable issues and route them to the correct team.

You must strictly follow the taxonomy provided below.

# Taxonomy

## Tutor

### Delivery

Quality of teaching, explanations, examples, demonstrations, presentation style.

Examples:

* Explanations are clear.
* Instructor uses good examples.
* Teaching style is confusing.

### Communication

Language clarity, speaking ability, responsiveness, interaction.

Examples:

* Hard to understand instructor.
* Tutor responds quickly.
* Communication is unclear.

### Knowledge

Subject expertise and accuracy.

Examples:

* Tutor is highly knowledgeable.
* Instructor gives incorrect information.

### Pace

Speed of teaching.

Examples:

* Too fast.
* Too slow.

---

## Content

### Difficulty

Content too easy or too difficult.

### Relevance

Content matches learning objectives and industry needs.

### Clarity

Content organization and understandability.

### Pace

Amount of content covered per unit or week.

---

## Assessment

### Fairness

Grading fairness and consistency.

### Difficulty

Assessment complexity.

### Alignment

Assessment matches taught material.

---

## Administration

### Scheduling

Timetable, deadlines, release dates.

### Communication

Administrative announcements and notifications.

---

## Tech

### Content

Broken learning materials, incorrect resources, inaccessible files.

### Assessment

Auto-grader issues, quiz bugs, submission problems.

### Platform

Login issues, crashes, outages, loading problems.

### Media

Audio, video, captions, streaming quality.

### UX

Navigation, usability, discoverability.

### Infra

Performance, servers, networking, lab environments.

---

## Unknown

Use only when feedback cannot reasonably fit any category.

# Actionability Rules

Mark actionable=false when feedback is:

1. Pure praise without improvement opportunity.
2. Pure personal preference.
3. Too vague to determine an action.
4. Not related to the course experience.

Examples:

"Great course."
-> actionable=false

"I personally hate Python."
-> actionable=false

"Nice."
-> actionable=false

# Multi-label Rules

A feedback may belong to multiple categories.

Example:

"The tutor explains well but the assignments are unfair."

Produces:

1. Tutor -> Delivery -> Positive
2. Assessment -> Fairness -> Negative

# Sentiment

Allowed values:

* positive
* negative
* neutral
* mixed

# Severity

Allowed values:

* critical
* high
* medium
* low

Severity should reflect business impact.

Critical:

* Prevents learning
* Prevents assessment completion
* Platform unavailable

High:

* Major learning obstacle
* Repeated grading failures
* Significant course quality issue

Medium:

* Noticeable but not blocking

Low:

* Minor inconvenience

# Summary

Generate a concise summary of the core issue in less than 20 words.

# Confidence

Return a decimal value between 0 and 1.

# Output Requirements

Return JSON only.

Never explain your reasoning.

Never invent new categories.

Never invent new subcategories.

Use only categories from the taxonomy that exactly match a `label` enum value
(e.g. "Tutor|Delivery"), and the exact schema provided.
"""

EXAMPLE_INPUT = (
    "The instructor explains concepts clearly and uses excellent examples."
)
EXAMPLE_OUTPUT = {
    "actionable": False,
    "summary": "Positive feedback on teaching quality.",
    "labels": [
        {
            "label": "Tutor|Delivery",
            "sentiment": "positive",
            "severity": "low",
            "confidence": 0.98,
        }
    ],
}

_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        (
            "human",
            """
Example:
Input: {example_input}
Output: {example_output}

Now classify:

{feedback}
""",
        ),
    ]
)


def get_model(provider: str = "openai"):
    settings = get_settings()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        return ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key,
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is not configured")
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            temperature=0,
            api_key=settings.google_api_key,
        )

    else:
        raise ValueError(f"Unknown provider: {provider!r}")


@lru_cache(maxsize=8)
def _get_chain(provider: str):
    llm = get_model(provider)
    structured_llm = llm.with_structured_output(FeedbackClassification)
    return _PROMPT | structured_llm


def classify_feedback(text: str, provider: str = "openai") -> FeedbackClassification:
    chain = _get_chain(provider)
    result = chain.invoke(
        {
            "example_input": EXAMPLE_INPUT,
            "example_output": EXAMPLE_OUTPUT,
            "feedback": text,
        }
    )
    return result
