"""
Text preprocessing pipeline, ported from Preprocessing.ipynb.

Steps:
1. Language detection + translation to English (langdetect + deep_translator,
   the lightweight approach from the notebook — avoids shipping a large
   transformers translation model in the service).
2. Removal of consecutive duplicate / gibberish lines.
3. PII redaction via regex patterns (email, phone, IP, URL, Aadhaar, PAN,
   credit card). Optional spaCy NER redaction (PERSON/ORG/GPE/LOC) is
   layered on top if the `en_core_web_sm` model is installed; the service
   degrades gracefully if it isn't.
"""
import re
from itertools import groupby
from typing import Optional, Tuple

from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

# --------------------------------------------------------------------------
# 1. Language detection + translation
# --------------------------------------------------------------------------


def detect_language(text: str) -> Optional[str]:
    try:
        return detect(text)
    except LangDetectException:
        return None


def translate_to_english(text: str, source_lang: Optional[str] = None) -> str:
    """Translate text to English. Falls back to the original text on failure
    (e.g. network unavailable, unsupported language)."""
    try:
        translator = GoogleTranslator(source=source_lang or "auto", target="en")
        return translator.translate(text)
    except Exception:
        return text


# --------------------------------------------------------------------------
# 2. Duplicate / gibberish line removal
# --------------------------------------------------------------------------

_CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{5,}")


def is_gibberish(word: str) -> bool:
    word = word.lower()

    if len(word) < 3:
        return False

    # Long consonant sequences
    if _CONSONANT_RUN.search(word):
        return True

    # Too few vowels
    vowels = sum(c in "aeiou" for c in word)
    if vowels / len(word) < 0.2:
        return True

    return False


def remove_consecutive_duplicates(lines, keep: int = 1):
    for _, group in groupby(lines):
        group = list(group)
        group = [g for g in group if not is_gibberish(g.strip())]
        yield from group[:keep]


def clean_lines(text: str) -> str:
    return "".join(remove_consecutive_duplicates(text.splitlines(True))).strip()


# --------------------------------------------------------------------------
# 3. PII redaction
# --------------------------------------------------------------------------

PII_PATTERNS = {
    "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    "PHONE": r"\b(?:\+91[- ]?)?[6-9]\d{9}\b",
    "IP": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "URL": r"https?://\S+|www\.\S+",
    "AADHAAR": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "PAN": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "CREDIT_CARD": r"\b(?:\d[ -]*?){13,16}\b",
}


def remove_pii_regex(text: str) -> str:
    for tag, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, f"[{tag}]", text)
    return text


_NLP = None
_SPACY_ENTITY_LABELS = {"PERSON", "ORG", "GPE", "LOC"}


def _get_spacy_model():
    """Lazily load spaCy's en_core_web_sm. Returns None if unavailable so the
    service still works without the extra ~50MB model / dependency."""
    global _NLP
    if _NLP is None:
        try:
            import spacy

            _NLP = spacy.load("en_core_web_sm")
        except Exception:
            _NLP = False  # sentinel: "tried and unavailable"
    return _NLP or None


def remove_named_entities(text: str) -> str:
    nlp = _get_spacy_model()
    if nlp is None:
        return text

    doc = nlp(text)
    new_text = text
    for ent in reversed(doc.ents):
        if ent.label_ in _SPACY_ENTITY_LABELS:
            new_text = (
                new_text[: ent.start_char] + f"[{ent.label_}]" + new_text[ent.end_char :]
            )
    return new_text


def redact_pii(text: str, use_ner: bool = True) -> str:
    text = remove_pii_regex(text)
    if use_ner:
        text = remove_named_entities(text)
    return text


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------


def preprocess(
    text: str,
    translate: bool = True,
    remove_pii: bool = True,
    remove_duplicates: bool = True,
) -> Tuple[Optional[str], Optional[str], str, str]:
    """Returns (detected_language, translated_text, cleaned_text, final_text)."""
    detected_language = None
    translated_text = None
    working_text = text

    if translate:
        detected_language = detect_language(text)
        if detected_language and detected_language != "en":
            translated_text = translate_to_english(text, detected_language)
            working_text = translated_text

    cleaned_text = clean_lines(working_text) if remove_duplicates else working_text

    final_text = redact_pii(cleaned_text) if remove_pii else cleaned_text

    return detected_language, translated_text, cleaned_text, final_text
