# Generated from: digital_evidence_intelligence_engine.ipynb
# Converted at: 2026-07-15T01:45:01.324Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # digital_evidence_intelligence_engine.py
# 
# ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)
# Notebook 4 - Digital Evidence Intelligence Engine
# 
# Mission (one sentence):
# Collect every possible digital evidence, extract useful information from
# it, normalize it into one standard format, preserve the original evidence,
# and hand a structured evidence package to the Fraud Intelligence Engine
# (Notebook 2).
# 
# Position in the pipeline:
# 
#   Citizen Input (voice, image, video, pdf, text, email, screenshot, chat)
#           |
#           v
#   Notebook 4 - Digital Evidence Intelligence Engine   <- this file
#           |
#           v
#   Notebook 2 - Fraud Intelligence Engine
#           |
#           v
#   Notebook 3 - Decision Intelligence Engine
# 
# Design principle: this notebook never performs fraud classification. It
# never says "Digital Arrest" or "UPI Fraud". It only knows evidence -
# files, transcripts, OCR text, metadata, hashes, timelines and quality
# scores. Fraud understanding is Notebook 2's job; deciding what to do
# about it is Notebook 3's job. This separation means Notebook 2 never has
# to know whether a piece of evidence arrived as a phone call, a WhatsApp
# screenshot, or an emailed PDF.
# 
# The case is born here: Case ID generation now lives in Notebook 4,
# because in real digital-forensics workflows a case begins the moment
# evidence is first submitted, not when an AI model first looks at it.
# 
# Revision 2 additions:
#   - Structured Evidence Context: instead of one flattened text blob,
#     Notebook 2 now receives a dict keyed by evidence type
#     (e.g. "call_transcript", "government_notice", "whatsapp_screenshot")
#     so it can reason about each evidence item individually instead of
#     re-parsing a wall of concatenated text.
#   - Organization Extraction: government/financial bodies mentioned in
#     the evidence (CBI, RBI, ED, Police, Court, Income Tax, Customs,
#     NPCI, SEBI, UIDAI, Cyber Cell) are identified here, once, so
#     Notebook 2 never has to re-detect them.
#   - Fine-grained Evidence Type: broad InputType (Audio/Image/PDF/Text)
#     is refined into a specific, reasoning-friendly label such as
#     "Government Notice", "WhatsApp Screenshot", "SMS", or
#     "Payment Screenshot", derived from source channel and content.


# ## Imports and Logging Setup


import hashlib
import json
import logging
import mimetypes
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("digital_evidence_intelligence_engine")

# Optional heavy dependencies. Each is wrapped so the pipeline degrades
# gracefully (with a clear log message) on a machine where the underlying
# engine or binary is not installed, instead of crashing the whole notebook.
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False

try:
    import speech_recognition as sr
    _SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    _SPEECH_RECOGNITION_AVAILABLE = False

try:
    from pypdf import PdfReader
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

# ## 1. Configuration


class Config:
    '''Central configuration for Notebook 4.'''

    SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
    SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
    SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
    SUPPORTED_PDF_EXTENSIONS = {".pdf"}
    SUPPORTED_TEXT_EXTENSIONS = {".txt", ".eml", ".msg"}

    MIN_TEXT_LENGTH_FOR_MEDIUM_QUALITY = 20
    MIN_TEXT_LENGTH_FOR_HIGH_QUALITY = 80

    CASE_ID_PREFIX = "CASE"


CONFIG = Config()
logger.info("Notebook 4 configuration loaded.")

# ## 2. Core Enums


class InputType(str, Enum):
    AUDIO = "Audio"
    IMAGE = "Image"
    VIDEO = "Video"
    PDF = "PDF"
    TEXT = "Text"
    EMAIL = "Email"
    UNKNOWN = "Unknown"


class EvidenceQuality(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    EXCELLENT = "Excellent"


class ProcessingStatus(str, Enum):
    SUCCESS = "Success"
    PARTIAL = "Partial"
    FAILED = "Failed"
    ENGINE_UNAVAILABLE = "Engine Unavailable"


class EvidenceIntelligenceError(Exception):
    '''Raised when Notebook 4 cannot produce a valid evidence package.'''

# ## 3. Module 1 - Input Controller


#
# Accepts one evidence item at a time. An "evidence item" describes a
# single citizen-submitted artifact: a file on disk plus a small amount of
# context about where it came from. This notebook does not fetch files
# from WhatsApp/email/telecom APIs itself - that integration work happens
# upstream; this module only validates what it is handed.


@dataclass
class EvidenceInput:
    file_path: Optional[str] = None          # path to the uploaded file, if any
    raw_text: Optional[str] = None            # direct text (SMS, chat, pasted message)
    source_channel: str = "Unknown"           # e.g. "WhatsApp", "Call", "Email", "Manual Upload"
    submitted_at: Optional[str] = None        # ISO timestamp of submission
    original_filename: Optional[str] = None
    # For sandboxes/tests where a real ASR/OCR engine is not deployed, an
    # upstream service may already have produced text (e.g. a production
    # STT microservice). Notebook 4's job is orchestration and
    # normalization - it is built to consume real engine output when
    # available and falls back to this override only when the underlying
    # engine cannot run in the current environment.
    override_extracted_text: Optional[str] = None


def ingest_input(evidence_input: EvidenceInput) -> EvidenceInput:
    '''Module 1 entry point. Validates that at least one usable payload exists.'''
    if not evidence_input.file_path and not evidence_input.raw_text:
        raise EvidenceIntelligenceError(
            "Evidence input has neither a file_path nor raw_text; nothing to process."
        )
    if evidence_input.file_path and not os.path.exists(evidence_input.file_path):
        raise EvidenceIntelligenceError(f"File not found: {evidence_input.file_path}")
    if not evidence_input.submitted_at:
        evidence_input.submitted_at = datetime.now(timezone.utc).isoformat()
    logger.info("Ingested evidence input. source_channel=%s file_path=%s",
                evidence_input.source_channel, evidence_input.file_path)
    return evidence_input

# ## 4. Module 2 - File Identification


#
# Pure routing. No AI, no fraud awareness - just "what kind of file is
# this", based on extension and, as a fallback, MIME type.

_EXTENSION_TO_TYPE: Dict[str, InputType] = {}
for ext in CONFIG.SUPPORTED_AUDIO_EXTENSIONS:
    _EXTENSION_TO_TYPE[ext] = InputType.AUDIO
for ext in CONFIG.SUPPORTED_IMAGE_EXTENSIONS:
    _EXTENSION_TO_TYPE[ext] = InputType.IMAGE
for ext in CONFIG.SUPPORTED_VIDEO_EXTENSIONS:
    _EXTENSION_TO_TYPE[ext] = InputType.VIDEO
for ext in CONFIG.SUPPORTED_PDF_EXTENSIONS:
    _EXTENSION_TO_TYPE[ext] = InputType.PDF
for ext in CONFIG.SUPPORTED_TEXT_EXTENSIONS:
    _EXTENSION_TO_TYPE[ext] = InputType.TEXT


def identify_input_type(evidence_input: EvidenceInput) -> InputType:
    '''Module 2 entry point.'''
    if evidence_input.raw_text and not evidence_input.file_path:
        return InputType.TEXT

    ext = os.path.splitext(evidence_input.file_path)[1].lower()
    if ext in _EXTENSION_TO_TYPE:
        return _EXTENSION_TO_TYPE[ext]

    guessed_mime, _ = mimetypes.guess_type(evidence_input.file_path)
    if guessed_mime:
        if guessed_mime.startswith("audio/"):
            return InputType.AUDIO
        if guessed_mime.startswith("image/"):
            return InputType.IMAGE
        if guessed_mime.startswith("video/"):
            return InputType.VIDEO
        if guessed_mime == "application/pdf":
            return InputType.PDF
        if guessed_mime.startswith("text/"):
            return InputType.TEXT

    logger.warning("Could not identify input type for %s; marking Unknown.", evidence_input.file_path)
    return InputType.UNKNOWN

# ## 4b. Module 2b - Evidence Type Classifier (fine-grained typing)


#
# InputType (above) answers "what file format is this" - useful for
# routing to the right extraction engine. This module answers a different,
# reasoning-facing question: "what kind of evidence is this, in terms a
# human investigator or Notebook 2 would use". A PDF might really be a
# "Government Notice"; an image might really be a "Payment Screenshot".
# Still no fraud judgement here - "Payment Screenshot" describes the
# evidence's form, not whether the payment was fraudulent.

_GOVERNMENT_NOTICE_KEYWORDS = (
    "notice", "warrant", "summons", "court", "reserve bank", "cbi",
    "enforcement directorate", "income tax department", "customs department",
    "final notice", "case number", "fir",
)
_PAYMENT_KEYWORDS = ("upi", "transaction", "transaction id", "paid", "payment successful", "amount")
_CURRENCY_KEYWORDS = ("counterfeit", "fake note", "currency note")


def classify_evidence_type(evidence_input: "EvidenceInput", input_type: InputType, text: str) -> str:
    '''Module 2b entry point. Returns a fine-grained, reasoning-friendly evidence type.'''
    channel = (evidence_input.source_channel or "").lower()
    lower_text = text.lower()

    if input_type == InputType.PDF:
        if any(k in lower_text for k in _GOVERNMENT_NOTICE_KEYWORDS):
            return "Government Notice"
        return "Document"

    if input_type == InputType.IMAGE:
        if any(k in lower_text for k in _CURRENCY_KEYWORDS) or "currency" in channel:
            return "Currency Image"
        if any(k in lower_text for k in _PAYMENT_KEYWORDS) or _AMOUNT_RE.search(text):
            return "Payment Screenshot"
        if "whatsapp" in channel:
            return "WhatsApp Screenshot"
        if "screenshot" in channel:
            return "Screenshot"
        return "Photo"

    if input_type == InputType.AUDIO:
        return "Call Recording"

    if input_type == InputType.VIDEO:
        return "Video Call Recording" if ("video" in channel or "call" in channel) else "Video Recording"

    if input_type == InputType.TEXT:
        if "sms" in channel:
            return "SMS"
        if "call" in channel:
            return "Call Transcript"
        if "email" in channel:
            return "Email"
        if "whatsapp" in channel or "chat" in channel:
            return "Chat Message"
        return "Text Message"

    if input_type == InputType.EMAIL:
        return "Email"

    return "Unclassified Evidence"


def _slugify_evidence_type(evidence_type: str) -> str:
    '''Turns "Government Notice" into "government_notice" for use as a dict key.'''
    return re.sub(r"[^a-z0-9]+", "_", evidence_type.lower()).strip("_")


def make_evidence_label(evidence_type: str, used_labels: set) -> str:
    '''
    Generates the key used in the Structured Evidence Context (Module 15).
    If a case already has one "call_transcript", a second one becomes
    "call_transcript_2" rather than overwriting the first.
    '''
    base = _slugify_evidence_type(evidence_type)
    if base not in used_labels:
        used_labels.add(base)
        return base
    counter = 2
    while f"{base}_{counter}" in used_labels:
        counter += 1
    label = f"{base}_{counter}"
    used_labels.add(label)
    return label

# ## 5. Extraction Result (shared by Modules 3-6)


@dataclass
class ExtractionResult:
    text: str
    status: str                 # ProcessingStatus value
    engine_used: str
    notes: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

# ## 6. Module 3 - Audio Evidence Processor


#
# Transcription only. No scam detection happens here - the transcript is
# handed to Notebook 2 exactly as extracted.


def process_audio(evidence_input: EvidenceInput) -> ExtractionResult:
    '''Module 3 entry point.'''
    if evidence_input.override_extracted_text is not None:
        return ExtractionResult(
            text=evidence_input.override_extracted_text,
            status=ProcessingStatus.SUCCESS.value,
            engine_used="upstream_stt_service (override)",
            notes=["Transcript supplied by an upstream speech-to-text service."],
        )

    if not _SPEECH_RECOGNITION_AVAILABLE:
        return ExtractionResult(
            text="", status=ProcessingStatus.ENGINE_UNAVAILABLE.value,
            engine_used="none",
            notes=["speech_recognition library is not installed; audio was not transcribed."],
        )

    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(evidence_input.file_path) as source:
            audio_data = recognizer.record(source)
        # NOTE: recognizer.recognize_google() requires outbound internet
        # access to a speech API. In an offline/sandboxed deployment this
        # call should be swapped for an on-prem/offline ASR engine (e.g.
        # Vosk, Whisper running locally). The call site is isolated here
        # specifically so that swap is a one-function change.
        transcript = recognizer.recognize_google(audio_data)
        return ExtractionResult(
            text=transcript, status=ProcessingStatus.SUCCESS.value,
            engine_used="speech_recognition(google)",
        )
    except Exception as exc:
        return ExtractionResult(
            text="", status=ProcessingStatus.FAILED.value,
            engine_used="speech_recognition",
            notes=[f"Audio transcription failed: {exc}"],
        )

# ## 7. Module 4 - Image Evidence Processor (OCR)


def process_image(evidence_input: EvidenceInput) -> ExtractionResult:
    '''Module 4 entry point. Screenshots, fake notices, payment screenshots, currency images.'''
    if evidence_input.override_extracted_text is not None:
        return ExtractionResult(
            text=evidence_input.override_extracted_text,
            status=ProcessingStatus.SUCCESS.value,
            engine_used="upstream_ocr_service (override)",
        )

    if not (_PIL_AVAILABLE and _TESSERACT_AVAILABLE):
        return ExtractionResult(
            text="", status=ProcessingStatus.ENGINE_UNAVAILABLE.value,
            engine_used="none",
            notes=["Pillow/pytesseract not available; image was not OCR'd."],
        )

    try:
        image = Image.open(evidence_input.file_path)
        text = pytesseract.image_to_string(image)
        return ExtractionResult(
            text=text.strip(), status=ProcessingStatus.SUCCESS.value,
            engine_used="pytesseract",
            extra={"image_size": image.size, "image_mode": image.mode},
        )
    except Exception as exc:
        return ExtractionResult(
            text="", status=ProcessingStatus.FAILED.value,
            engine_used="pytesseract",
            notes=[f"OCR failed: {exc}"],
        )

# ## 8. Module 5 - Video Evidence Processor


#
# Video = audio track (speech) + frames (OCR of on-screen text, e.g. a
# fraudulent caller ID overlay or a shared document). Frame extraction
# needs an external tool (ffmpeg/opencv) which this notebook treats as a
# pluggable dependency, same pattern as audio/image.


def process_video(evidence_input: EvidenceInput) -> ExtractionResult:
    '''Module 5 entry point.'''
    if evidence_input.override_extracted_text is not None:
        return ExtractionResult(
            text=evidence_input.override_extracted_text,
            status=ProcessingStatus.SUCCESS.value,
            engine_used="upstream_video_pipeline (override)",
            notes=["Video already processed by an upstream audio+frame extraction pipeline."],
        )
    # A production build would: extract the audio track (ffmpeg), run it
    # through process_audio(); extract periodic frames and run them
    # through process_image(); then merge both text streams. That
    # requires ffmpeg/opencv, which is not assumed to be present here.
    return ExtractionResult(
        text="", status=ProcessingStatus.ENGINE_UNAVAILABLE.value,
        engine_used="none",
        notes=["Video frame/audio extraction requires ffmpeg/opencv, not available in this environment.",
               "Supply override_extracted_text from an upstream video pipeline in production."],
    )

# ## 9. Module 6 - PDF Processor


def process_pdf(evidence_input: EvidenceInput) -> ExtractionResult:
    '''Module 6 entry point. Court notices, RBI/ED/CBI letters, statements.'''
    if evidence_input.override_extracted_text is not None:
        return ExtractionResult(
            text=evidence_input.override_extracted_text,
            status=ProcessingStatus.SUCCESS.value,
            engine_used="upstream_pdf_service (override)",
        )

    if not _PYPDF_AVAILABLE:
        return ExtractionResult(
            text="", status=ProcessingStatus.ENGINE_UNAVAILABLE.value,
            engine_used="none",
            notes=["pypdf not available; PDF was not read."],
        )

    try:
        reader = PdfReader(evidence_input.file_path)
        pages_text = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages_text).strip()
        status = ProcessingStatus.SUCCESS.value if text else ProcessingStatus.PARTIAL.value
        notes = [] if text else ["PDF opened successfully but no extractable text was found (likely a scanned/image PDF; route through OCR instead)."]
        return ExtractionResult(
            text=text, status=status, engine_used="pypdf",
            notes=notes, extra={"page_count": len(reader.pages)},
        )
    except Exception as exc:
        return ExtractionResult(
            text="", status=ProcessingStatus.FAILED.value,
            engine_used="pypdf",
            notes=[f"PDF extraction failed: {exc}"],
        )


def process_text(evidence_input: EvidenceInput) -> ExtractionResult:
    '''Handles raw text, SMS, chat, and email bodies passed directly as text.'''
    if evidence_input.raw_text is not None:
        return ExtractionResult(text=evidence_input.raw_text, status=ProcessingStatus.SUCCESS.value, engine_used="direct_text")
    try:
        with open(evidence_input.file_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        return ExtractionResult(text=content, status=ProcessingStatus.SUCCESS.value, engine_used="file_read")
    except Exception as exc:
        return ExtractionResult(text="", status=ProcessingStatus.FAILED.value, engine_used="file_read",
                                 notes=[f"Text file read failed: {exc}"])


_PROCESSORS = {
    InputType.AUDIO: process_audio,
    InputType.IMAGE: process_image,
    InputType.VIDEO: process_video,
    InputType.PDF: process_pdf,
    InputType.TEXT: process_text,
    InputType.EMAIL: process_text,
}

# ## 10. Module 7 - Metadata Extraction


#
# Regex-based extraction only. No AI, no fraud judgement - just pulling
# out structured fields that Notebook 2 and Notebook 3 will find useful.

_PHONE_RE = re.compile(r"(?:\+91[\-\s]?|0)?[6-9]\d{9}\b")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_UPI_RE = re.compile(r"\b[\w.\-]{2,256}@[a-zA-Z]{2,64}\b")
_URL_RE = re.compile(r"https?://[^\s)>\]]+")
_AMOUNT_RE = re.compile(r"(?:Rs\.?|INR|\u20B9)\s?[\d,]+(?:\.\d+)?", re.IGNORECASE)
_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

# Organization detection: full-phrase matches (case-insensitive) plus a
# short list of acronyms that must appear as a case-sensitive whole word,
# to avoid an all-lowercase word like "ed" false-matching "Enforcement
# Directorate". No fraud judgement is made about the organization mention
# itself - a citizen could legitimately mention "RBI"; Notebook 2 decides
# what that means in context.
_ORGANIZATION_PHRASES: Dict[str, List[str]] = {
    "CBI": ["central bureau of investigation"],
    "RBI": ["reserve bank of india"],
    "ED": ["enforcement directorate"],
    "Income Tax Department": ["income tax department", "income tax office"],
    "Customs": ["customs department", "customs office"],
    "Police": ["police station", "cyber police"],
    "Court": ["high court", "supreme court", "district court"],
    "NPCI": ["national payments corporation of india"],
    "SEBI": ["securities and exchange board of india"],
    "UIDAI": ["unique identification authority of india"],
    "Cyber Cell": ["cyber cell", "cyber crime cell"],
}
_ORGANIZATION_ACRONYMS: Dict[str, str] = {
    "CBI": "CBI", "RBI": "RBI", "ED": "ED", "NPCI": "NPCI", "SEBI": "SEBI", "UIDAI": "UIDAI",
}
_ORGANIZATION_GENERIC_WORDS: Dict[str, str] = {
    "police": "Police",
    "court": "Court",
}


def extract_organizations(text: str) -> List[str]:
    '''
    Module 7b entry point (Organization Extraction).

    Identifies government/financial/law-enforcement bodies mentioned in
    the evidence so Notebook 2 does not have to re-detect them from raw
    text. Deterministic phrase and acronym matching only.
    '''
    found: set = set()
    lower_text = text.lower()

    for org, phrases in _ORGANIZATION_PHRASES.items():
        if any(phrase in lower_text for phrase in phrases):
            found.add(org)

    for org, acronym in _ORGANIZATION_ACRONYMS.items():
        if re.search(rf"\b{acronym}\b", text):  # case-sensitive: only counts if written as the acronym
            found.add(org)

    for word, org in _ORGANIZATION_GENERIC_WORDS.items():
        if re.search(rf"\b{word}\b", lower_text):
            found.add(org)

    return sorted(found)


def extract_metadata(text: str) -> Dict[str, List[str]]:
    '''Module 7 entry point.'''
    phones = sorted(set(_PHONE_RE.findall(text)))
    emails = sorted(set(_EMAIL_RE.findall(text)))
    urls = sorted(set(_URL_RE.findall(text)))
    amounts = sorted(set(_AMOUNT_RE.findall(text)))
    dates = sorted(set(_DATE_RE.findall(text)))
    organizations = extract_organizations(text)

    # UPI IDs look like emails but usually end in a known handle
    # (@okhdfcbank, @ybl, @paytm, etc.) rather than a real mail domain.
    upi_handles = {"upi", "okhdfcbank", "ybl", "paytm", "oksbi", "okaxis", "ibl", "axl", "apl"}
    all_handle_like = set(_UPI_RE.findall(text))
    upi_ids = sorted({h for h in all_handle_like if h.split("@")[-1].lower() in upi_handles})
    # Anything handle-like but not flagged as a UPI ID and not already an
    # email is left alone - metadata extraction should not over-claim.

    return {
        "phone_numbers": list(phones),
        "emails": list(emails),
        "upi_ids": upi_ids,
        "urls": list(urls),
        "amounts": list(amounts),
        "dates": list(dates),
        "organizations": organizations,
    }

# ## 11. Module 8 - OCR Intelligence (bounding boxes / confidence)


#
# A step beyond plain OCR text: where on the image the text sat, and how
# confident the engine was. Useful later for highlighting suspicious
# regions (e.g. a spoofed logo) without doing any fraud judgement here.


def extract_ocr_intelligence(evidence_input: EvidenceInput, input_type: InputType) -> Optional[Dict[str, Any]]:
    '''Module 8 entry point. Only runs for image evidence with tesseract available.'''
    if input_type != InputType.IMAGE or not (_PIL_AVAILABLE and _TESSERACT_AVAILABLE):
        return None
    if not evidence_input.file_path:
        return None
    try:
        image = Image.open(evidence_input.file_path)
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        boxes = []
        for i in range(len(data.get("text", []))):
            word = data["text"][i].strip()
            if not word:
                continue
            boxes.append({
                "word": word,
                "confidence": data["conf"][i],
                "left": data["left"][i], "top": data["top"][i],
                "width": data["width"][i], "height": data["height"][i],
            })
        avg_conf = (
            sum(b["confidence"] for b in boxes if isinstance(b["confidence"], (int, float)) and b["confidence"] >= 0) / len(boxes)
            if boxes else 0
        )
        return {"word_boxes": boxes, "average_confidence": round(avg_conf, 1)}
    except Exception as exc:
        logger.warning("OCR intelligence extraction failed: %s", exc)
        return None

# ## 12. Module 9 - Evidence Integrity Engine


#
# Hashing and provenance metadata so an investigator can later prove the
# evidence was not modified after submission.


def compute_evidence_integrity(evidence_input: EvidenceInput) -> Dict[str, Any]:
    '''Module 9 entry point.'''
    if not evidence_input.file_path:
        # Text-only submissions still get a hash of their content.
        content_bytes = (evidence_input.raw_text or "").encode("utf-8")
        return {
            "sha256": hashlib.sha256(content_bytes).hexdigest(),
            "original_name": None,
            "size_bytes": len(content_bytes),
            "extension": None,
            "captured_at": evidence_input.submitted_at,
        }

    sha256 = hashlib.sha256()
    with open(evidence_input.file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha256.update(chunk)

    return {
        "sha256": sha256.hexdigest(),
        "original_name": evidence_input.original_filename or os.path.basename(evidence_input.file_path),
        "size_bytes": os.path.getsize(evidence_input.file_path),
        "extension": os.path.splitext(evidence_input.file_path)[1].lower(),
        "captured_at": evidence_input.submitted_at,
    }

# ## 13. Module 10 - Evidence Timeline Builder


def build_evidence_timeline(evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    '''
    Module 10 entry point.

    Sorts already-processed evidence items chronologically by their
    submission timestamp so the final package tells a story: what arrived
    first, second, third.
    '''
    def _sort_key(item: Dict[str, Any]) -> str:
        return item.get("submitted_at") or ""

    ordered = sorted(evidence_items, key=_sort_key)
    return [
        {
            "timestamp": item.get("submitted_at"),
            "input_type": item.get("input_type"),
            "evidence_type": item.get("evidence_type"),
            "source_channel": item.get("source_channel"),
            "summary": (item.get("text") or "")[:120],
        }
        for item in ordered
    ]

# ## 14. Module 11 - Evidence Relationship Builder


def build_evidence_relationships(evidence_items: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    '''
    Module 11 entry point.

    Links evidence items that share the same extracted entity (phone
    number, email, UPI ID, URL). Output maps entity -> list of evidence
    indices ("evidence-0", "evidence-1", ...) that mention it, which is
    exactly the edge list the Fraud Network Graph Engine (Notebook 6) will
    want later.
    '''
    relationships: Dict[str, List[str]] = {}
    for idx, item in enumerate(evidence_items):
        evidence_ref = f"evidence-{idx}"
        metadata = item.get("metadata", {})
        for field_name in ("phone_numbers", "emails", "upi_ids", "urls", "organizations"):
            for value in metadata.get(field_name, []):
                key = f"{field_name}:{value}"
                relationships.setdefault(key, []).append(evidence_ref)

    # Only entities that appear in more than one evidence item represent an
    # actual relationship worth surfacing.
    return {k: v for k, v in relationships.items() if len(v) > 1}

# ## 15. Module 12 - Language Detection


#
# Lightweight Unicode-block heuristic - no external API call, so it works
# fully offline. Good enough to route Notebook 2 to the right prompt
# language; not a substitute for a real language-ID model in production.

_UNICODE_LANGUAGE_RANGES: List[Tuple[str, int, int]] = [
    ("Hindi/Marathi (Devanagari)", 0x0900, 0x097F),
    ("Tamil", 0x0B80, 0x0BFF),
    ("Kannada", 0x0C80, 0x0CFF),
    ("Telugu", 0x0C00, 0x0C7F),
    ("Gujarati", 0x0A80, 0x0AFF),
    ("Punjabi (Gurmukhi)", 0x0A00, 0x0A7F),
]


def detect_language(text: str) -> str:
    '''Module 12 entry point.'''
    if not text.strip():
        return "Unknown"
    counts: Dict[str, int] = {}
    for ch in text:
        code_point = ord(ch)
        for label, start, end in _UNICODE_LANGUAGE_RANGES:
            if start <= code_point <= end:
                counts[label] = counts.get(label, 0) + 1
                break
    if not counts:
        return "English"  # default: Latin-script text with no other script detected
    return max(counts, key=counts.get)

# ## 16. Module 13 - Evidence Quality Assessment


def assess_evidence_quality(extraction: ExtractionResult, input_type: InputType) -> str:
    '''Module 13 entry point.'''
    if extraction.status in (ProcessingStatus.FAILED.value, ProcessingStatus.ENGINE_UNAVAILABLE.value):
        return EvidenceQuality.LOW.value

    text_length = len(extraction.text.strip())

    if input_type == InputType.IMAGE:
        avg_conf = extraction.extra.get("ocr_average_confidence")
        if avg_conf is not None:
            if avg_conf >= 85 and text_length >= CONFIG.MIN_TEXT_LENGTH_FOR_HIGH_QUALITY:
                return EvidenceQuality.EXCELLENT.value
            if avg_conf >= 60:
                return EvidenceQuality.HIGH.value
            if avg_conf >= 35:
                return EvidenceQuality.MEDIUM.value
            return EvidenceQuality.LOW.value

    if text_length >= CONFIG.MIN_TEXT_LENGTH_FOR_HIGH_QUALITY:
        return EvidenceQuality.HIGH.value
    if text_length >= CONFIG.MIN_TEXT_LENGTH_FOR_MEDIUM_QUALITY:
        return EvidenceQuality.MEDIUM.value
    if text_length > 0:
        return EvidenceQuality.LOW.value
    return EvidenceQuality.LOW.value

# ## 17. Module 14 - Duplicate Detection


def find_duplicates(evidence_items: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    '''
    Module 14 entry point.

    Groups evidence items by their SHA-256 hash. Any hash shared by more
    than one item means the citizen (or the intake channel) submitted the
    exact same file/content more than once.
    '''
    by_hash: Dict[str, List[str]] = {}
    for idx, item in enumerate(evidence_items):
        digest = item.get("integrity", {}).get("sha256")
        if not digest:
            continue
        by_hash.setdefault(digest, []).append(f"evidence-{idx}")
    return {h: refs for h, refs in by_hash.items() if len(refs) > 1}

# ## 18. Case ID Generation


#
# Moved here from Notebook 3: the case begins the moment evidence is first
# submitted, not when the AI model first analyzes it.


def generate_case_id() -> str:
    return f"{CONFIG.CASE_ID_PREFIX}-{uuid.uuid4().hex[:8].upper()}"

# ## 19. Module 15 / 17 - Evidence Packaging & Standard Output


def process_single_evidence(evidence_input: EvidenceInput) -> Dict[str, Any]:
    '''
    Runs Modules 1-9, 12 and 13 for one evidence item and returns its
    processed record. This is the per-item building block that
    package_case_evidence() below assembles into a full case.
    '''
    evidence_input = ingest_input(evidence_input)
    input_type = identify_input_type(evidence_input)

    processor = _PROCESSORS.get(input_type)
    if processor is None:
        extraction = ExtractionResult(
            text="", status=ProcessingStatus.ENGINE_UNAVAILABLE.value,
            engine_used="none", notes=[f"No processor registered for input type {input_type.value}."],
        )
    else:
        extraction = processor(evidence_input)

    metadata = extract_metadata(extraction.text)
    ocr_intel = extract_ocr_intelligence(evidence_input, input_type)
    if ocr_intel is not None:
        extraction.extra["ocr_average_confidence"] = ocr_intel["average_confidence"]

    integrity = compute_evidence_integrity(evidence_input)
    language = detect_language(extraction.text)
    quality = assess_evidence_quality(extraction, input_type)
    evidence_type = classify_evidence_type(evidence_input, input_type, extraction.text)

    record = {
        "input_type": input_type.value,
        "evidence_type": evidence_type,
        "source_channel": evidence_input.source_channel,
        "submitted_at": evidence_input.submitted_at,
        "text": extraction.text,
        "extraction_status": extraction.status,
        "engine_used": extraction.engine_used,
        "processing_notes": extraction.notes,
        "metadata": metadata,
        "ocr_intelligence": ocr_intel,
        "integrity": integrity,
        "language": language,
        "evidence_quality": quality,
    }
    logger.info(
        "Processed evidence item. type=%s evidence_type=%s status=%s quality=%s engine=%s",
        input_type.value, evidence_type, extraction.status, quality, extraction.engine_used,
    )
    return record


def package_case_evidence(
    evidence_inputs: List[EvidenceInput],
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    '''
    Notebook 4 orchestration - Modules 1-17 combined.

    Accepts one or more EvidenceInput items belonging to the same citizen
    report and returns a single Standard Evidence Package: exactly the
    shape Notebook 2 expects, regardless of how many files came in or what
    channel they arrived on. The primary payload is `structured_evidence`
    - a dict keyed by evidence type (e.g. "call_transcript",
    "government_notice") - so Notebook 2 can reason about each item on
    its own rather than re-parsing one flattened text blob.
    '''
    if not evidence_inputs:
        raise EvidenceIntelligenceError("No evidence items were submitted.")

    case_id = case_id or generate_case_id()

    evidence_items = [process_single_evidence(ei) for ei in evidence_inputs]

    # Assign each item a stable label (e.g. "call_transcript",
    # "government_notice", "whatsapp_screenshot") derived from its
    # fine-grained evidence_type, disambiguating duplicates with a suffix.
    used_labels: set = set()
    for item in evidence_items:
        item["evidence_label"] = make_evidence_label(item["evidence_type"], used_labels)

    timeline = build_evidence_timeline(evidence_items)
    relationships = build_evidence_relationships(evidence_items)
    duplicates = find_duplicates(evidence_items)

    # Structured Evidence Context: the primary payload for Notebook 2.
    # Instead of one flattened block of text, each evidence item is kept
    # under its own key so Notebook 2 can reason about each piece of
    # evidence individually (e.g. treat a "government_notice" differently
    # from a "call_transcript") rather than re-parsing a wall of text.
    structured_evidence: Dict[str, str] = {}
    structured_evidence_detail: Dict[str, Dict[str, Any]] = {}
    for item in evidence_items:
        if not item["text"].strip():
            continue
        label = item["evidence_label"]
        structured_evidence[label] = item["text"]
        structured_evidence_detail[label] = {
            "evidence_type": item["evidence_type"],
            "input_type": item["input_type"],
            "source_channel": item["source_channel"],
            "submitted_at": item["submitted_at"],
            "language": item["language"],
            "evidence_quality": item["evidence_quality"],
            "organizations_mentioned": item["metadata"].get("organizations", []),
        }

    # Legacy flattened text, kept only for simple consumers that expect a
    # single string; Notebook 2 should prefer structured_evidence above.
    combined_text_blocks = [
        f"[{item['evidence_label']} | {item['evidence_type']}]\n{item['text']}"
        for item in evidence_items if item["text"].strip()
    ]
    combined_text = "\n\n".join(combined_text_blocks)

    # Merge metadata across all evidence items (deduplicated).
    merged_metadata: Dict[str, List[str]] = {}
    for item in evidence_items:
        for key, values in item["metadata"].items():
            merged_metadata.setdefault(key, [])
            for v in values:
                if v not in merged_metadata[key]:
                    merged_metadata[key].append(v)

    # Case-level language: the language of whichever evidence item has the
    # most text, since that's most likely to drive Notebook 2's prompt choice.
    language_candidates = [(len(item["text"]), item["language"]) for item in evidence_items if item["language"] != "Unknown"]
    case_language = max(language_candidates, key=lambda t: t[0])[1] if language_candidates else "Unknown"

    # Case-level quality: the weakest link, since Notebook 2's confidence
    # should not exceed what the worst piece of evidence supports.
    quality_rank = {EvidenceQuality.LOW.value: 0, EvidenceQuality.MEDIUM.value: 1,
                    EvidenceQuality.HIGH.value: 2, EvidenceQuality.EXCELLENT.value: 3}
    case_quality = min((item["evidence_quality"] for item in evidence_items), key=lambda q: quality_rank.get(q, 0))

    unavailable_engines = sorted({
        item["engine_used"] for item in evidence_items
        if item["extraction_status"] == ProcessingStatus.ENGINE_UNAVAILABLE.value
    })

    package: Dict[str, Any] = {
        # --- Standard output contract for Notebook 2 ---
        "case_id": case_id,
        "structured_evidence": structured_evidence,
        "structured_evidence_detail": structured_evidence_detail,
        "text": combined_text,   # legacy flattened fallback; prefer structured_evidence
        "language": case_language,
        "metadata": merged_metadata,
        "evidence_quality": case_quality,
        "source": evidence_items[0]["source_channel"] if len(evidence_items) == 1 else "Multiple",
        "next_engine": "Fraud Intelligence Engine",

        # --- Full evidence detail, preserved for investigators ---
        "evidence_objects": evidence_items,
        "timeline": timeline,
        "relationships": relationships,
        "duplicates": duplicates,
        "engines_unavailable": unavailable_engines,
        "packaged_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "Case %s packaged. items=%d quality=%s language=%s duplicates=%d relationships=%d",
        case_id, len(evidence_items), case_quality, case_language, len(duplicates), len(relationships),
    )
    return package

# ## 20. Sample Inputs and Deterministic Test Suite


#
# Because real speech-to-text/OCR engines depend on the deployment
# environment, the test suite demonstrates the full pipeline using a mix
# of genuinely processed evidence (a real PDF, run through pypdf) and
# override_extracted_text for channels whose real engine is not present in
# this environment (clearly flagged in each item's processing_notes).


def _build_sample_pdf(path: str) -> None:
    '''Creates a tiny real, well-formed PDF so process_pdf() can be exercised for real.'''
    try:
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(path, pagesize=(612, 792))
        c.setFont("Helvetica", 14)
        c.drawString(50, 700, "RESERVE BANK OF INDIA - FINAL NOTICE.")
        c.drawString(50, 680, "Your account will be frozen unless verified within 24 hours.")
        c.save()
    except Exception as exc:
        logger.warning("Could not build sample PDF (%s); PDF module will report a failure/unavailable status instead.", exc)


def run_notebook4_test_suite() -> Dict[str, Any]:
    sample_dir = "/tmp/notebook4_samples"
    os.makedirs(sample_dir, exist_ok=True)
    pdf_path = os.path.join(sample_dir, "fake_rbi_notice.pdf")
    _build_sample_pdf(pdf_path)

    # A minimal real image file so the WhatsApp screenshot evidence item is
    # correctly routed through the Image branch (extension-based typing),
    # even though its text is supplied via override_extracted_text rather
    # than run through pytesseract in this sample.
    whatsapp_image_path = os.path.join(sample_dir, "whatsapp_payment_screenshot.jpg")
    try:
        from PIL import Image as _PILImage
        _PILImage.new("RGB", (10, 10), color="white").save(whatsapp_image_path)
    except Exception as exc:
        logger.warning("Could not build sample image (%s); writing a placeholder file instead.", exc)
        with open(whatsapp_image_path, "wb") as fh:
            fh.write(b"placeholder")

    # A single citizen report bundling multiple evidence channels - the
    # scenario Notebook 4 exists for.
    evidence_inputs = [
        EvidenceInput(
            raw_text="Sir this is CBI, your Aadhaar is linked to a money laundering case. "
                     "Call back on 9876543210 immediately or a warrant will be issued.",
            source_channel="Call Transcript (STT override)",
            submitted_at="2026-07-12T09:30:00+00:00",
            override_extracted_text="Sir this is CBI, your Aadhaar is linked to a money laundering case. "
                                     "Call back on 9876543210 immediately or a warrant will be issued.",
        ),
        EvidenceInput(
            raw_text=None,
            file_path=pdf_path,
            source_channel="Email Attachment",
            submitted_at="2026-07-12T09:37:00+00:00",
            original_filename="fake_rbi_notice.pdf",
        ),
        EvidenceInput(
            raw_text=None,
            file_path=whatsapp_image_path,
            source_channel="WhatsApp Screenshot",
            submitted_at="2026-07-12T09:40:00+00:00",
            original_filename="whatsapp_payment_screenshot.jpg",
            override_extracted_text="Pay Rs 50,000 to rahul.verify@okhdfcbank now to avoid arrest. "
                                     "Contact 9876543210 or rahul.verify@gmail.com",
        ),
    ]

    package = package_case_evidence(evidence_inputs)

    print("=== Notebook 4 Test Suite: Digital Arrest bundle (call + PDF + screenshot) ===\n")

    checks = []

    def _check(label: str, actual: Any, expected: Any) -> None:
        ok = actual == expected
        checks.append(ok)
        print(f"    [{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")

    _check("case_id starts with prefix", package["case_id"].startswith(CONFIG.CASE_ID_PREFIX), True)
    _check("evidence item count", len(package["evidence_objects"]), 3)
    _check("next_engine", package["next_engine"], "Fraud Intelligence Engine")
    _check("phone number captured", "9876543210" in package["metadata"].get("phone_numbers", []), True)
    _check("upi id captured", "rahul.verify@okhdfcbank" in package["metadata"].get("upi_ids", []), True)
    _check("email captured", "rahul.verify@gmail.com" in package["metadata"].get("emails", []), True)
    _check("amount captured", any("50,000" in a for a in package["metadata"].get("amounts", [])), True)
    _check("relationship found for shared phone number", "phone_numbers:9876543210" in package["relationships"], True)
    _check("pdf text extracted", "RESERVE BANK OF INDIA" in package["evidence_objects"][1]["text"].upper(), True)
    _check("timeline is chronological", [t["timestamp"] for t in package["timeline"]] == sorted(t["timestamp"] for t in package["timeline"]), True)

    # --- New checks: organization extraction ---
    _check("CBI detected in call transcript", "CBI" in package["metadata"].get("organizations", []), True)
    _check("RBI detected in PDF notice", "RBI" in package["metadata"].get("organizations", []), True)

    # --- New checks: fine-grained evidence typing ---
    _check("call item typed as Call Transcript", package["evidence_objects"][0]["evidence_type"], "Call Transcript")
    _check("PDF item typed as Government Notice", package["evidence_objects"][1]["evidence_type"], "Government Notice")
    _check("screenshot item typed as Payment Screenshot",
           package["evidence_objects"][2]["evidence_type"], "Payment Screenshot")

    # --- New checks: structured evidence context ---
    _check("structured_evidence has call_transcript key", "call_transcript" in package["structured_evidence"], True)
    _check("structured_evidence has government_notice key", "government_notice" in package["structured_evidence"], True)
    _check("structured_evidence has payment_screenshot key", "payment_screenshot" in package["structured_evidence"], True)
    _check(
        "structured_evidence values are plain strings, not blobs",
        all(isinstance(v, str) for v in package["structured_evidence"].values()), True,
    )

    print(f"\nSUMMARY: {sum(checks)}/{len(checks)} checks passed\n")

    print("Case-level package summary:")
    print(f"  case_id           = {package['case_id']}")
    print(f"  evidence_quality  = {package['evidence_quality']}")
    print(f"  language          = {package['language']}")
    print(f"  source            = {package['source']}")
    print(f"  organizations     = {package['metadata'].get('organizations', [])}")
    print(f"  engines_unavailable = {package['engines_unavailable']}")
    print(f"  duplicates        = {package['duplicates']}")
    print(f"  relationships     = {list(package['relationships'].keys())}")

    print("\nStructured Evidence Context handed to Notebook 2:")
    print(json.dumps(package["structured_evidence"], indent=2, ensure_ascii=False))

    print("\nStructured Evidence Detail (per item):")
    print(json.dumps(package["structured_evidence_detail"], indent=2, ensure_ascii=False))

    print("\nEvidence timeline:")
    for entry in package["timeline"]:
        print(f"  {entry['timestamp']} | {entry['input_type']:6s} | {entry['source_channel']}")

    return package


if __name__ == "__main__":
    run_notebook4_test_suite()