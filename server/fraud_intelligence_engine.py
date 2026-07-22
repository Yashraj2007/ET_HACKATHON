# Generated from: Fraud_Intelligence_Engine.ipynb
# Converted at: 2026-07-22T00:00:00.000Z (Revision: FIX-2026-07-22)
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # Notebook 2: Fraud Intelligence Engine
# ### ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)
#
# FIX-2026-07-22 (this revision) — two bugs fixed based on the Notebook 8
# orchestrator run log:
#
# 1. ROOT CAUSE OF THE 404s: `google/gemini-2.0-flash-exp:free` (and before
#    that `qwen/qwen2.5-72b-instruct:free`) is a single hardcoded OpenRouter
#    ":free" model ID. Free-tier model IDs on OpenRouter rotate in and out
#    of availability without notice — that's exactly what produced
#    `"No endpoints found for google/gemini-2.0-flash-exp:free"` on every
#    single case. Fix: CONFIG.OPENROUTER_MODEL_CANDIDATES is now an ordered
#    LIST of models. `_call_openrouter` walks the list and only moves to the
#    next candidate on a 404 ("model not found / no endpoints") — any other
#    error (auth, timeout, malformed response) still raises immediately so
#    real problems aren't masked.
#
# 2. `FraudIntelligenceError` was *referenced* in `analyze_case()`'s except
#    block but was **never defined anywhere in the file**. That is why the
#    orchestrator's fallback path logged
#    `error=name 'FraudIntelligenceError' is not defined` — the real
#    exception (the 404) was being swallowed by a second, unrelated
#    NameError. It is now defined as a proper Exception subclass near the
#    top of the file, right after the logging setup.
#
# This notebook implements the six-module Fraud Intelligence Engine:
#
# 1. Signal Extraction
# 2. Knowledge Retrieval (RAG)
# 3. LLM Reasoning (OpenRouter, multi-model fallback)
# 3b. Indicator Normalisation
# 4. Fraud Classification (Deterministic)
# 5. Evidence Validation
# 6. Rule-based Risk Engine
#
# followed by full pipeline orchestration, sample test cases, notes/limitations, and a standalone deterministic test suite.


# ## 1. Imports and Logging Configuration


"""
Core imports for the Fraud Intelligence Engine.

chromadb              - reads the persistent vector store created in Notebook 1
sentence_transformers - encodes the user query with the same embedding model
                        used in Notebook 1, so vectors are comparable
requests              - OpenRouter API client used for the reasoning module
difflib               - lightweight fuzzy matching for indicator normalisation
"""

import difflib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import chromadb
import requests
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fraud_intelligence_engine")

# Module version, exposed so external orchestrators (e.g. Notebook 8) can
# read it via getattr(module, "ENGINE_VERSION", "unknown") instead of
# guessing which revision of this file is actually loaded.
ENGINE_VERSION = "2.2"


# ---------------------------------------------------------------------------
# FIX-2026-07-22: FraudIntelligenceError was used throughout this module
# (analyze_case, _run_sample_cases, run_test_suite) but was never actually
# defined. Any real failure inside analyze_case() (e.g. the OpenRouter 404)
# was being masked by a second NameError when Python tried to raise this
# undefined name. It is now a proper exception class, defined once, right
# after logging setup, so every downstream `raise FraudIntelligenceError(...)`
# and `except FraudIntelligenceError` actually works.
# ---------------------------------------------------------------------------
class FraudIntelligenceError(Exception):
    """Raised when the Notebook 2 pipeline fails to analyse a case."""
    pass


# ## 2. Configuration


class Config:
    """
    Central configuration for Notebook 2.

    These values must stay consistent with Notebook 1's knowledge base
    build configuration.
    """

    # --- Knowledge base (must match Notebook 1) ---
    CHROMA_PERSIST_DIR: str = "./knowledge_vector_db"
    CHROMA_COLLECTION_NAME: str = "fraud_scam_knowledge_base"
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

    # --- Retrieval ---
    TOP_K: int = 5
    MIN_RELEVANCE_SCORE: float = 0.1

    # --- OpenRouter ---
    # FIX-2026-07-22: free-tier model IDs on OpenRouter rotate constantly.
    # A single hardcoded model name (previously
    # "google/gemini-2.0-flash-exp:free", and before that
    # "qwen/qwen2.5-72b-instruct:free") will eventually 404 with
    # "No endpoints found for <model>". Instead we keep an ORDERED list of
    # candidates and walk it on 404s. Update this list if OpenRouter's free
    # catalog changes again — check https://openrouter.ai/models before
    # relying on any single ID long-term.
    OPENROUTER_MODEL_CANDIDATES: List[str] = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-coder:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "google/gemma-3-27b-it:free",
        "openrouter/free",  # last resort: OpenRouter's own auto-router over free models
    ]
    # Kept for backwards compatibility with any code/logs that read a single
    # model name; always equal to the first candidate.
    OPENROUTER_MODEL_NAME: str = OPENROUTER_MODEL_CANDIDATES[0]

    # FIX-2026-07-10: this must be the NAME of an environment variable,
    # never the key itself. The previous version had a real key pasted
    # here directly, which leaked it into version control / shared files.
    OPENROUTER_API_KEY_ENV_VAR: str = "OPENROUTER_API_KEY"

    OPENROUTER_API_URL: str = "https://openrouter.ai/api/v1/chat/completions"
    LLM_TEMPERATURE: float = 0.2

    # FIX-2026-07-10: root cause of the JSON truncation crash.
    # Reasoning models draw hidden "thinking" tokens from the same
    # max_tokens budget as the final answer unless a reasoning-specific
    # budget is set. With max_tokens=2048 the model was spending almost
    # everything on reasoning and getting cut off mid-string while writing
    # the "explanation" field.
    LLM_MAX_OUTPUT_TOKENS: int = 4096
    LLM_REASONING_MAX_TOKENS: int = 1024

    # If a response is still truncated (finish_reason == "length"), retry
    # once with this larger budget before giving up on a clean parse.
    LLM_RETRY_MAX_OUTPUT_TOKENS: int = 6144
    LLM_MAX_RETRIES: int = 1

    # --- Indicator normalisation ---
    INDICATOR_FUZZY_MATCH_CUTOFF: float = 0.6

    # --- Fraud classification ---
    CLASSIFICATION_MIN_OVERLAP_RATIO: float = 0.4
    UNCLASSIFIED_LABEL: str = "Unclassified Suspicious Activity"

    # --- Risk engine ---
    RISK_LOW_MAX: int = 30
    RISK_MEDIUM_MAX: int = 60
    RISK_HIGH_MAX: int = 85


CONFIG = Config()
logger.info(
    "Configuration loaded. persist_dir=%s collection=%s model_candidates=%s",
    CONFIG.CHROMA_PERSIST_DIR,
    CONFIG.CHROMA_COLLECTION_NAME,
    CONFIG.OPENROUTER_MODEL_CANDIDATES,
)

# ## 3. Module 1 - Signal Extraction


@dataclass
class SignalExtractionResult:
    """
    Structured output of Module 1.

    entities   - regex-extracted structured data points
    behaviours - boolean-style behavioural flags detected in the text
    raw_matches - the literal substrings that triggered each behavioural flag
    """

    entities: Dict[str, List[str]] = field(default_factory=dict)
    behaviours: Dict[str, bool] = field(default_factory=dict)
    raw_matches: Dict[str, List[str]] = field(default_factory=dict)

# --- Entity regex patterns -------------------------------------------------

_PATTERNS: Dict[str, str] = {
    "phone_numbers": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    "upi_ids": r"\b[\w.\-]{2,256}@[a-zA-Z]{2,64}\b",
    "pan_numbers": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "aadhaar_numbers": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "bank_accounts": r"\b\d{9,18}\b",
    "urls": r"https?://[^\s]+|www\.[^\s]+",
    "otp_mentions": r"\bOTP\b|\bone[- ]time password\b",
    "money_amounts": r"(?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?(?:\s?(?:lakh|crore|k))?",
}

# --- Behavioural keyword groups ---------------------------------------------

_BEHAVIOUR_KEYWORD_GROUPS: Dict[str, List[str]] = {
    "authority_impersonation": [
        "cbi",
        "ed",
        "enforcement directorate",
        "rbi",
        "income tax department",
        "trai",
        "cyber cell",
        "cyber crime branch",
        "police department",
        "customs department",
        "narcotics",
        "supreme court",
        "high court",
    ],
    "threat_language": [
        "arrest warrant",
        "you will be arrested",
        "legal action",
        "fir will be filed",
        "case will be registered",
        "jail",
        "criminal case",
        "non bailable",
    ],
    "urgency": [
        "immediately",
        "right now",
        "within 30 minutes",
        "urgent",
        "act fast",
        "last warning",
        "final notice",
        "before it is too late",
    ],
    "isolation_tactics": [
        "do not disconnect",
        "don't disconnect",
        "do not tell anyone",
        "keep this confidential",
        "do not hang up",
        "stay on the call",
        "do not inform your family",
    ],
    "payment_request": [
        "transfer",
        "pay a fine",
        "processing fee",
        "refundable deposit",
        "security deposit",
        "verification fee",
        "send money",
        "pay now",
    ],
    "criminal_allegation": [
        "money laundering",
        "your aadhaar is linked",
        "parcel contains drugs",
        "illegal activity",
        "your account is involved",
        "under investigation",
    ],
    "qr_code_fraud": [
        "qr",
        "scan qr",
        "qr code",
        "scan to receive",
        "scanner",
    ],
    "investment_fraud": [
        "investment",
        "stock trading",
        "trading profit",
        "guaranteed return",
        "crypto profit",
        "stock tips",
    ],
    "job_fraud": [
        "part-time job",
        "telegram task",
        "like video",
        "google review task",
        "daily income",
    ],
    "customer_care_fraud": [
        "anydesk",
        "teamviewer",
        "quicksupport",
        "helpline",
        "customer care",
        "refund claim",
    ],
}

def _extract_entities(text: str) -> Dict[str, List[str]]:
    """Run every regex pattern against the text and collect unique matches."""
    entities: Dict[str, List[str]] = {}
    for label, pattern in _PATTERNS.items():
        found = re.findall(pattern, text, flags=re.IGNORECASE)
        seen: List[str] = []
        for item in found:
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        if seen:
            entities[label] = seen
    return entities

def _extract_behaviours(
    text: str,
) -> Tuple[Dict[str, bool], Dict[str, List[str]]]:
    """Detect behavioural / linguistic signals via keyword matching."""
    lowered = text.lower()
    behaviours: Dict[str, bool] = {}
    matches: Dict[str, List[str]] = {}

    for behaviour_name, keywords in _BEHAVIOUR_KEYWORD_GROUPS.items():
        found_terms = [kw for kw in keywords if kw in lowered]
        behaviours[behaviour_name] = len(found_terms) > 0
        if found_terms:
            matches[behaviour_name] = found_terms

    return behaviours, matches

def extract_signals(text: str) -> SignalExtractionResult:
    """
    Module 1 entry point.

    Extracts entities and behavioural signals from raw user-reported text.
    Does not classify the case. Raises ValueError on empty input.
    """
    if not text or not text.strip():
        raise ValueError("extract_signals received empty input text.")

    entities = _extract_entities(text)
    behaviours, matches = _extract_behaviours(text)

    result = SignalExtractionResult(
        entities=entities, behaviours=behaviours, raw_matches=matches
    )
    logger.info(
        "Signal extraction complete. entities=%d behaviour_flags=%d",
        len(entities),
        sum(1 for v in behaviours.values() if v),
    )
    return result

# ## 4. Module 2 - Knowledge Retrieval (RAG)


_embedding_model: Optional[SentenceTransformer] = None
_chroma_collection = None


def _get_embedding_model() -> SentenceTransformer:
    """Lazily load the sentence-transformers model used in Notebook 1."""
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading embedding model: %s", CONFIG.EMBEDDING_MODEL_NAME)
        _embedding_model = SentenceTransformer(CONFIG.EMBEDDING_MODEL_NAME)
    return _embedding_model

def _get_chroma_collection():
    """
    Connect to the existing ChromaDB collection created in Notebook 1.

    Automatically checks both `./knowledge_vector_db` and relative server directories
    to ensure the knowledge base is located.
    """
    global _chroma_collection
    if _chroma_collection is None:
        candidate_paths = [
            CONFIG.CHROMA_PERSIST_DIR,
            os.path.join(os.path.dirname(__file__), "knowledge_vector_db"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "knowledge_vector_db")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server", "knowledge_vector_db")),
        ]
        
        found_client = None
        found_path = None
        
        for path in candidate_paths:
            if not os.path.exists(path):
                continue
            try:
                client = chromadb.PersistentClient(path=path)
                existing_names = [c.name for c in client.list_collections()]
                if CONFIG.CHROMA_COLLECTION_NAME in existing_names:
                    found_client = client
                    found_path = path
                    break
            except Exception:
                continue

        if found_client is None:
            raise RuntimeError(
                f"ChromaDB collection '{CONFIG.CHROMA_COLLECTION_NAME}' "
                f"was not found in any of the checked paths: {candidate_paths}."
            )

        _chroma_collection = found_client.get_collection(CONFIG.CHROMA_COLLECTION_NAME)
        logger.info(
            "Connected to ChromaDB collection '%s' (%d documents) at '%s'.",
            CONFIG.CHROMA_COLLECTION_NAME,
            _chroma_collection.count(),
            found_path,
        )
    return _chroma_collection

@dataclass
class RetrievedChunk:
    """One retrieved knowledge base chunk with its metadata."""

    text: str
    source_document: str
    category: str
    metadata: Dict[str, Any]
    relevance_score: float

def _resolve_source_document(meta: Dict[str, Any]) -> str:
    """
    Resolve the source document name across possible metadata key names.
    """
    return (
        meta.get("source_file")
        or meta.get("source_document")
        or meta.get("doc_id")
        or "unknown"
    )

def _l2_distance_to_similarity(distance: float) -> float:
    """
    Convert a ChromaDB L2 distance to a 0-1 similarity score.

    ChromaDB's default metric for PersistentClient is L2 (squared Euclidean).
    Values range from 0 (identical vectors) upward with no fixed maximum.

    Formula: similarity = 1 / (1 + distance)
    - distance = 0   -> similarity = 1.0
    - distance = 1   -> similarity = 0.5
    - distance = 9   -> similarity = 0.1

    This is monotone-decreasing, so ranking is preserved.
    """
    return 1.0 / (1.0 + float(distance))

def retrieve_evidence(query: str, top_k: int = None) -> List[RetrievedChunk]:
    """
    Module 2 entry point.

    Embeds the query with the same model used in Notebook 1, queries
    ChromaDB for the top-k most relevant chunks, and returns them with
    their source metadata. Filters out chunks below MIN_RELEVANCE_SCORE.
    """
    if not query or not query.strip():
        raise ValueError("retrieve_evidence received empty query text.")

    top_k = top_k or CONFIG.TOP_K
    model = _get_embedding_model()
    collection = _get_chroma_collection()

    query_embedding = model.encode(query).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    chunks: List[RetrievedChunk] = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc_text, meta, distance in zip(documents, metadatas, distances):
        meta = meta or {}
        relevance_score = _l2_distance_to_similarity(distance)

        if relevance_score < CONFIG.MIN_RELEVANCE_SCORE:
            continue

        chunks.append(
            RetrievedChunk(
                text=doc_text,
                source_document=_resolve_source_document(meta),
                category=meta.get("category", "uncategorised"),
                metadata=meta,
                relevance_score=round(relevance_score, 4),
            )
        )

    logger.info(
        "Retrieved %d relevant chunks (of %d candidates) for query.",
        len(chunks),
        len(documents),
    )
    return chunks

# ## 5. Module 3 - LLM Reasoning (OpenRouter, multi-model fallback)


def _get_openrouter_api_key() -> str:
    """
    Return the OpenRouter API key from the environment.

    FIX-2026-07-10: no hardcoded fallback key anymore. A real key was
    previously embedded directly in this file - that key should be
    treated as compromised and rotated on openrouter.ai immediately.
    This function now fails loudly instead of silently using a leaked
    key, so the mistake can't happen again.
    """
    api_key = os.environ.get(CONFIG.OPENROUTER_API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"Environment variable '{CONFIG.OPENROUTER_API_KEY_ENV_VAR}' is not "
            f"set. Set it before running this notebook, e.g.:\n"
            f"  import os\n"
            f"  os.environ['{CONFIG.OPENROUTER_API_KEY_ENV_VAR}'] = '<your key>'\n"
            f"Never hardcode API keys directly in notebook/source files."
        )
    return api_key

_REASONING_SYSTEM_INSTRUCTIONS = """\
You are a fraud intelligence reasoning engine for a Digital Public Safety
platform. You analyse a citizen-reported conversation using only the
extracted signals and the retrieved official evidence provided to you.

Rules you must follow strictly:
1. Reason only from the evidence given to you. Do not invent facts.
2. If the retrieved evidence is insufficient to support a conclusion,
   explicitly say so instead of guessing.
3. Identify fraud indicators as short labels (for example
   'Government Impersonation', 'Threat Language', 'Urgent Payment Request').
   Only use 'Government Impersonation' when the message explicitly claims
   to be from a specific government agency, police force, or official body
   (e.g. "I am from CBI", "this is the Income Tax Department"). Do NOT use
   it just because the message mentions arrest, criminal case, or legal
   action in general - use 'Threat Language' or 'Criminal Allegation' for
   that instead.
   Do NOT decide the overall fraud type or category yourself.
   Do NOT output a numeric risk score.
   Both are computed by deterministic logic downstream from your indicators.
4. Do not recommend any action to the citizen, bank, police or telecom
   operator. Your only job is to explain what is happening.
5. Keep the "explanation" field to at most 3 sentences. Be concise -
   your entire response must fit comfortably within the output budget.
6. Your ENTIRE response must be a single raw JSON object - no markdown fences,
   no prose before or after it - with exactly these four keys:
     "indicators"         : array of short indicator strings
     "llm_confidence"     : integer 0-100
     "evidence_sufficient": boolean
     "explanation"        : short paragraph grounded in the evidence
"""

def _build_reasoning_prompt(
    user_input: str,
    signals: SignalExtractionResult,
    retrieved_chunks: List[RetrievedChunk],
) -> str:
    """Assemble the user-turn prompt combining input, signals, and evidence."""
    try:
        signals_block = json.dumps(
            {"entities": signals.entities, "behaviours": signals.behaviours},
            indent=2,
            default=str,
        )
    except Exception as e:
        logger.warning("Failed to serialize signals: %s", e)
        signals_block = str({"entities": signals.entities, "behaviours": signals.behaviours})

    if retrieved_chunks:
        evidence_block = "\n\n".join(
            f"[Source: {c.source_document} | Category: {c.category} | "
            f"Relevance: {c.relevance_score}]\n{c.text}"
            for c in retrieved_chunks
        )
    else:
        evidence_block = (
            "No relevant documents were retrieved from the knowledge base."
        )

    return (
        f"Citizen-reported conversation:\n{json.dumps(user_input)}\n\n"
        f"Extracted signals:\n{signals_block}\n\n"
        f"Retrieved official evidence:\n{evidence_block}\n\n"
        f"Based only on the above, return the JSON object described in "
        f"your instructions. Output ONLY the raw JSON - no markdown, no prose."
    )

def _extract_json_from_text(text: str) -> str:
    """
    Best-effort extraction of the first complete JSON object from arbitrary
    text. Handles three cases in priority order:

    1. The whole text (after stripping fences) is already valid JSON.
    2. There is a {...} block somewhere in the text.
    3. The text contains a JSON object spread across multiple lines.
    """
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    text = text.strip()

    if text.startswith("{"):
        return text

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        return match.group(0)

    return text

def _repair_truncated_json(text: str) -> str:
    """
    FIX-2026-07-10: last-resort repair for a JSON object that was cut off
    mid-generation (finish_reason == "length"). This is a heuristic, not
    a full parser - it handles the common truncation shapes we actually
    saw (cut off mid-string, or mid-array/object) well enough to recover
    the fields that were already fully written.

    Strategy:
    1. If we're mid-string (odd number of unescaped double quotes), close
       the string.
    2. Trim any dangling trailing comma.
    3. Close any open arrays/objects in the correct order based on a
       simple bracket-depth scan.
    """
    repaired = text

    # Count unescaped double quotes to detect an unterminated string.
    unescaped_quotes = len(re.findall(r'(?<!\\)"', repaired))
    if unescaped_quotes % 2 == 1:
        repaired += '"'

    # Drop a trailing comma (with optional whitespace) right before EOF.
    repaired = re.sub(r",\s*$", "", repaired)

    # Walk the string tracking bracket depth (ignoring bracket chars that
    # occur inside string literals) to build the correct closing sequence.
    stack: List[str] = []
    in_string = False
    escape_next = False
    for ch in repaired:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()

    closers = {"{": "}", "[": "]"}
    while stack:
        opener = stack.pop()
        repaired += closers[opener]

    return repaired

def _extract_text_from_response(response_json: Dict[str, Any]) -> str:
    """
    Extract the model's final answer text from an OpenRouter response.

    Reasoning-capable models may return their answer in different places
    depending on whether they used extended thinking:

    Shape A - normal:
        choices[0].message.content = "<the answer>"
        choices[0].message.reasoning_details = [...]   (chain-of-thought)

    Shape B - reasoning-only (content is None or ""):
        choices[0].message.content = None / ""
        choices[0].message.reasoning_details = [
            {"type": "thinking", "thinking": "...chain of thought..."},
            {"type": "text",     "text":     "<the answer>"}   <- last item
        ]

    Shape C - reasoning_details absent, everything in content:
        choices[0].message.content = "<the answer>"

    This function tries each shape in order and returns the first non-empty
    string it finds.
    """
    message = response_json["choices"][0]["message"]
    content: str = (message.get("content") or "").strip()
    reasoning_details: List[Dict] = message.get("reasoning_details") or []

    if content:
        logger.debug("Response shape: content field is populated (Shape A/C).")
        return content

    if reasoning_details:
        text_blocks = [
            item.get("text", "")
            for item in reasoning_details
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if text_blocks:
            logger.debug(
                "Response shape: answer found in reasoning_details 'text' block "
                "(Shape B). %d text block(s) found, using last.",
                len(text_blocks),
            )
            return text_blocks[-1].strip()

        thinking_blocks = [
            item.get("thinking", "")
            for item in reasoning_details
            if isinstance(item, dict) and item.get("type") == "thinking"
        ]
        if thinking_blocks:
            combined = "\n".join(thinking_blocks)
            logger.debug(
                "Response shape: no 'text' block; falling back to 'thinking' "
                "content (%d chars).",
                len(combined),
            )
            return combined

    logger.warning(
        "Could not extract any text from OpenRouter response: %s",
        json.dumps(response_json, default=str)[:500],
    )
    return ""


class _ModelUnavailableError(RuntimeError):
    """
    Raised internally when OpenRouter returns a 404 / 'no endpoints found'
    for a specific model. Distinct from a generic RuntimeError so
    run_llm_reasoning knows to move on to the next model candidate instead
    of giving up on the whole case.
    """
    pass


def _call_openrouter(
    messages: List[Dict[str, Any]], max_output_tokens: int, model_name: str
) -> Dict[str, Any]:
    """
    POST to OpenRouter for a specific model and return the parsed response JSON.

    Raises _ModelUnavailableError specifically on a 404 "no endpoints found"
    style response (the model itself is gone/renamed) so the caller can try
    the next candidate model. Raises RuntimeError for any other HTTP error
    (auth failure, rate limit, timeout, etc.) since those are not fixed by
    switching models.
    """
    api_key = _get_openrouter_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": CONFIG.LLM_TEMPERATURE,
        "max_tokens": max_output_tokens,
        # FIX-2026-07-10: cap the hidden reasoning budget so it can't
        # consume the whole max_tokens allowance and starve the final
        # JSON answer, which is what caused the truncation crash.
        "reasoning": {"max_tokens": CONFIG.LLM_REASONING_MAX_TOKENS},
        # FIX-2026-07-11: removed "response_format": {"type": "json_object"}.
        # Some providers reject it outright ("does not support 'json_object'
        # response format... supported formats: json_schema"), causing an
        # immediate 400 on every call. We rely instead on the system prompt
        # instruction plus _extract_json_from_text / _repair_truncated_json
        # downstream, which already handle malformed/truncated output
        # robustly across providers.
    }

    response = requests.post(
        CONFIG.OPENROUTER_API_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=180,
    )

    if response.status_code == 404:
        # FIX-2026-07-22: this is the exact failure mode from the log
        # ("No endpoints found for <model>:free"). It means the model ID
        # itself is unavailable right now, not that something is wrong
        # with the request. Signal this distinctly so run_llm_reasoning
        # can move on to the next candidate model.
        raise _ModelUnavailableError(
            f"Model '{model_name}' is unavailable on OpenRouter right now "
            f"(HTTP 404): {response.text}"
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"OpenRouter API request failed for model '{model_name}' with "
            f"status {response.status_code}: {response.text}"
        )

    parsed = response.json()

    if "choices" not in parsed or not parsed["choices"]:
        raise RuntimeError(
            f"OpenRouter response for model '{model_name}' contained no "
            f"choices: {json.dumps(parsed)}"
        )

    return parsed

def _synthesize_rag_reasoning(
    user_input: str,
    signals: SignalExtractionResult,
    retrieved_chunks: List[RetrievedChunk],
) -> Dict[str, Any]:
    """
    Local dynamic RAG intelligence synthesizer used when OpenRouter API Key is unconfigured or offline.
    Extracts indicators, matches RAG chunks from ChromaDB, and builds evidence-derived reasoning.
    """
    indicators = []
    # Map extracted signals & RAG chunks to indicators dynamically
    for behaviour, active in signals.behaviours.items():
        if active:
            label = behaviour.replace("_", " ").title()
            if label not in indicators:
                indicators.append(label)

    # Check top retrieved chunks for additional indicator context
    sources = []
    for chunk in retrieved_chunks:
        if chunk.category and chunk.category not in indicators:
            indicators.append(chunk.category.replace("_", " ").title())
        if chunk.source_document and chunk.source_document not in sources:
            sources.append(chunk.source_document)

    top_relevance = retrieved_chunks[0].relevance_score if retrieved_chunks else 0.5
    confidence = int(min(92.0, max(50.0, top_relevance * 100.0 + len(indicators) * 5.0)))

    matched_sources_str = ", ".join(sources[:3]) if sources else "ChromaDB Fraud Taxonomy"
    extracted_entities_str = ", ".join([f"{k}: {v}" for k, v in signals.entities.items() if v])

    explanation = (
        f"Dynamic RAG analysis matched {len(retrieved_chunks)} knowledge vectors from {matched_sources_str}. "
        f"Detected behavioral signals: {', '.join(indicators) if indicators else 'Suspicious Communication'}. "
        f"Extracted entities: {extracted_entities_str if extracted_entities_str else 'None'}."
    )

    return {
        "indicators": indicators if indicators else ["Suspicious Pattern"],
        "llm_confidence": confidence,
        "evidence_sufficient": len(retrieved_chunks) > 0 or len(signals.behaviours) > 0,
        "explanation": explanation,
        "_model_used": "chromadb_rag_synthesizer",
    }


def run_llm_reasoning(
    user_input: str,
    signals: SignalExtractionResult,
    retrieved_chunks: List[RetrievedChunk],
) -> Dict[str, Any]:
    """
    Module 3 entry point.

    Walks CONFIG.OPENROUTER_MODEL_CANDIDATES in order if OPENROUTER_API_KEY is configured.
    Otherwise uses local dynamic RAG intelligence synthesis over ChromaDB knowledge base.
    """
    api_key = os.environ.get(CONFIG.OPENROUTER_API_KEY_ENV_VAR)
    if not api_key:
        logger.info(
            "OPENROUTER_API_KEY environment variable not set. Running local dynamic RAG synthesizer over ChromaDB vector store."
        )
        return _synthesize_rag_reasoning(user_input, signals, retrieved_chunks)

    user_prompt = _build_reasoning_prompt(user_input, signals, retrieved_chunks)

    messages = [
        {"role": "system", "content": _REASONING_SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_prompt},
    ]

    last_raw_text = ""
    last_model_error: Optional[Exception] = None

    for model_name in CONFIG.OPENROUTER_MODEL_CANDIDATES:
        token_budget = CONFIG.LLM_MAX_OUTPUT_TOKENS

        try:
            for attempt in range(CONFIG.LLM_MAX_RETRIES + 1):
                logger.info(
                    "Sending request to OpenRouter (%s), attempt %d, max_tokens=%d.",
                    model_name,
                    attempt + 1,
                    token_budget,
                )
                response_json = _call_openrouter(messages, token_budget, model_name)

                finish_reason = (
                    response_json.get("choices", [{}])[0].get("finish_reason", "")
                )
                was_truncated = finish_reason == "length"

                raw_text = _extract_text_from_response(response_json)
                last_raw_text = raw_text or last_raw_text

                if not raw_text:
                    logger.error(
                        "Model '%s' returned completely empty text. Full response: %s",
                        model_name,
                        json.dumps(response_json, default=str)[:2000],
                    )
                    if attempt < CONFIG.LLM_MAX_RETRIES:
                        token_budget = CONFIG.LLM_RETRY_MAX_OUTPUT_TOKENS
                        time.sleep(1)
                        continue
                    last_model_error = ValueError(
                        f"Model '{model_name}' returned an empty response after retries."
                    )
                    break

                cleaned = _extract_json_from_text(raw_text)

                try:
                    parsed = json.loads(cleaned)
                except json.JSONDecodeError as exc:
                    if was_truncated and attempt < CONFIG.LLM_MAX_RETRIES:
                        token_budget = CONFIG.LLM_RETRY_MAX_OUTPUT_TOKENS
                        time.sleep(1)
                        continue

                    repaired = _repair_truncated_json(cleaned)
                    try:
                        parsed = json.loads(repaired)
                    except json.JSONDecodeError as exc2:
                        last_model_error = ValueError(
                            f"Failed to parse LLM output from '{model_name}' as JSON: {exc2}"
                        )
                        break

                required_defaults = {
                    "indicators": [],
                    "llm_confidence": 0,
                    "evidence_sufficient": False,
                    "explanation": "[Response was truncated; partial data shown.]",
                }
                missing = set(required_defaults) - parsed.keys()
                if missing:
                    for key in missing:
                        parsed[key] = required_defaults[key]

                parsed["_model_used"] = model_name
                return parsed

            continue

        except _ModelUnavailableError as exc:
            logger.warning(
                "Model '%s' unavailable on OpenRouter; trying next candidate. Detail: %s",
                model_name,
                exc,
            )
            last_model_error = exc
            continue

    logger.warning(
        "OpenRouter candidates unavailable or failing (%s); falling back to local dynamic RAG synthesizer.",
        last_model_error,
    )
    return _synthesize_rag_reasoning(user_input, signals, retrieved_chunks)

# ## 6. Module 3b - Indicator Normalisation


_CANONICAL_INDICATOR_SYNONYMS: Dict[str, List[str]] = {
    "Government Impersonation": [
        "government impersonation",
        "government official impersonation",
        "authority impersonation",
        "police impersonation",
        "cbi impersonation",
        "impersonating a government agency",
        "impersonation of bank official",
        "official impersonation",
    ],
    "Threat Language": [
        "threat language",
        "fear tactics",
        "intimidation",
        "legal threat",
        "threatening language",
        "coercion",
    ],
    "Urgency": [
        "urgency",
        "time pressure",
        "urgent request",
        "artificial urgency",
    ],
    "Isolation Tactics": [
        "isolation",
        "isolation tactics",
        "do not disconnect instruction",
        "keep this confidential instruction",
    ],
    "Money Demand": [
        "money demand",
        "urgent transfer request",
        "payment demand",
        "fund transfer request",
        "demand for money",
        "financial demand",
    ],
    "Urgent Payment Request": [
        "urgent payment request",
        "immediate payment demand",
        "request for immediate transfer",
    ],
    "Criminal Allegation": [
        "criminal allegation",
        "false criminal accusation",
        "accusation of a crime",
        "false legal accusation",
    ],
    "Suspicious Link": [
        "suspicious link",
        "phishing link",
        "malicious url",
        "fake link",
    ],
    "OTP Request": [
        "otp request",
        "otp phishing",
        "request for otp",
        "asking for otp",
    ],
    "Blackmail / Extortion Threat": [
        "blackmail",
        "extortion",
        "extortion threat",
        "sextortion",
        "private photo blackmail",
        "photo leak threat",
        "leak threat",
        "threat to leak",
        "threat to expose",
        "compromising photo threat",
        "compromising video threat",
    ],
    "QR Code Fraud": [
        "qr code fraud",
        "qr code scam",
        "scan qr code",
        "qr scanning fraud",
        "qr code",
    ],
    "Investment Fraud": [
        "investment fraud",
        "investment scam",
        "stock trading fraud",
        "crypto investment scam",
        "trading scam",
        "stock tips scam",
    ],
    "Job Fraud": [
        "job fraud",
        "part-time job scam",
        "telegram task scam",
        "video like task",
        "job scam",
    ],
    "Customer Care Fraud": [
        "customer care fraud",
        "anydesk scam",
        "teamviewer scam",
        "helpline fraud",
        "refund scam",
    ],
}

_SYNONYM_TO_CANONICAL: Dict[str, str] = {
    synonym.lower(): canonical
    for canonical, synonyms in _CANONICAL_INDICATOR_SYNONYMS.items()
    for synonym in synonyms + [canonical]
}
_ALL_SYNONYMS_LOWER: List[str] = list(_SYNONYM_TO_CANONICAL.keys())

def normalize_indicator(raw_indicator: str) -> str:
    """
    Map a raw indicator string from the LLM onto a canonical indicator
    label. Falls back to fuzzy matching, then to the original string if no
    sufficiently close match is found.
    """
    cleaned = raw_indicator.strip().lower()
    if not cleaned:
        return raw_indicator

    if cleaned in _SYNONYM_TO_CANONICAL:
        return _SYNONYM_TO_CANONICAL[cleaned]

    close_matches = difflib.get_close_matches(
        cleaned,
        _ALL_SYNONYMS_LOWER,
        n=1,
        cutoff=CONFIG.INDICATOR_FUZZY_MATCH_CUTOFF,
    )
    if close_matches:
        return _SYNONYM_TO_CANONICAL[close_matches[0]]

    return raw_indicator.strip()

def normalize_indicators(raw_indicators: List[str]) -> List[str]:
    """
    Normalise a list of raw indicators and de-duplicate the result while
    preserving order.
    """
    normalized: List[str] = []
    seen: set = set()
    for raw in raw_indicators:
        canonical = normalize_indicator(raw)
        key = canonical.lower()
        if key not in seen:
            seen.add(key)
            normalized.append(canonical)
    return normalized

# ## 7. Module 4 - Fraud Classification (Deterministic)


_FRAUD_TYPE_SIGNATURES: Dict[str, List[str]] = {
    "Digital Arrest Scam": [
        "Government Impersonation",
        "Threat Language",
        "Isolation Tactics",
        "Criminal Allegation",
        "Urgent Payment Request",
    ],
    "QR Code / Payment Scam": [
        "QR Code Fraud",
        "Payment Request",
        "Urgent Payment Request",
    ],
    "Investment / Stock Trading Fraud": [
        "Investment Fraud",
        "Money Demand",
    ],
    "Job / Part-Time Work Fraud": [
        "Job Fraud",
    ],
    "Customer Care / Refund Fraud": [
        "Customer Care Fraud",
    ],
    "UPI / Payment Fraud": [
        "Money Demand",
        "Urgent Payment Request",
        "Suspicious Link",
        "OTP Request",
    ],
    "Phishing / Credential Theft": [
        "Suspicious Link",
        "OTP Request",
        "Urgency",
    ],
    "Extortion / Threat-based Fraud": [
        "Threat Language",
        "Criminal Allegation",
        "Money Demand",
        "Blackmail / Extortion Threat",
    ],
}

def _overlap_ratio(case_indicators: set, signature_indicators: List[str]) -> float:
    """Fraction of a signature's indicators that are present in the case."""
    if not signature_indicators:
        return 0.0
    matched = case_indicators & set(signature_indicators)
    return len(matched) / len(signature_indicators)

def classify_fraud_type(normalized_indicators: List[str]) -> Dict[str, Any]:
    """
    Module 4 entry point.

    Deterministically maps normalised indicators to the best-matching
    fraud type using fixed signatures.
    """
    if not normalized_indicators:
        return {
            "fraud_type": CONFIG.UNCLASSIFIED_LABEL,
            "match_ratio": 0.0,
            "candidates": {},
        }

    case_set = set(normalized_indicators)
    scores: Dict[str, float] = {
        fraud_type: _overlap_ratio(case_set, signature)
        for fraud_type, signature in _FRAUD_TYPE_SIGNATURES.items()
    }

    best_fraud_type = max(scores, key=scores.get)
    best_score = scores[best_fraud_type]

    chosen = (
        best_fraud_type
        if best_score >= CONFIG.CLASSIFICATION_MIN_OVERLAP_RATIO
        else CONFIG.UNCLASSIFIED_LABEL
    )

    logger.info(
        "Fraud classification complete. chosen=%s best_ratio=%.2f",
        chosen,
        best_score,
    )
    return {
        "fraud_type": chosen,
        "match_ratio": round(best_score, 4),
        "candidates": {k: round(v, 4) for k, v in scores.items()},
    }

# ## 8. Module 5 - Evidence Validation


@dataclass
class ValidationResult:
    """Output of Module 5, feeding into the final confidence score."""

    adjusted_confidence: int
    validation_notes: str
    category_match_ratio: float

def _category_relates_to_fraud_type(category: str, fraud_type: str) -> bool:
    """
    Loose relatedness check between a retrieved chunk's category and the
    classified fraud type.
    """

    def _normalize(s: str) -> set:
        return set(re.findall(r"[a-z0-9]+", s.lower()))

    category_tokens = _normalize(category)
    fraud_type_tokens = _normalize(fraud_type)
    if not category_tokens or not fraud_type_tokens:
        return False
    return len(category_tokens & fraud_type_tokens) > 0

def validate_evidence(
    llm_output: Dict[str, Any],
    classification: Dict[str, Any],
    retrieved_chunks: List[RetrievedChunk],
) -> ValidationResult:
    """
    Module 5 entry point.

    Adjusts the LLM's self-reported confidence based on retrieval strength,
    category relatedness to the classified fraud type, and whether the LLM
    itself flagged the evidence as insufficient.
    """
    base_confidence = int(llm_output.get("llm_confidence", 0))
    evidence_sufficient = bool(llm_output.get("evidence_sufficient", False))
    fraud_type = classification.get("fraud_type", CONFIG.UNCLASSIFIED_LABEL)

    if not retrieved_chunks:
        return ValidationResult(
            adjusted_confidence=max(0, base_confidence - 40),
            validation_notes=(
                "No supporting documents were retrieved; confidence reduced sharply."
            ),
            category_match_ratio=0.0,
        )

    if not evidence_sufficient:
        return ValidationResult(
            adjusted_confidence=max(0, base_confidence - 25),
            validation_notes=(
                "The model flagged retrieved evidence as insufficient; "
                "confidence reduced."
            ),
            category_match_ratio=0.0,
        )

    related_flags = [
        _category_relates_to_fraud_type(c.category, fraud_type)
        for c in retrieved_chunks
    ]
    category_match_ratio = sum(related_flags) / len(related_flags)
    avg_relevance = (
        sum(c.relevance_score for c in retrieved_chunks) / len(retrieved_chunks)
    )

    if category_match_ratio >= 0.5 and avg_relevance >= 0.6:
        adjusted = min(100, base_confidence + 15)
        notes = (
            "Retrieved documents are both highly relevant and match the "
            "classified fraud type's category; confidence increased."
        )
    elif category_match_ratio >= 0.5:
        adjusted = min(100, base_confidence + 5)
        notes = (
            "Retrieved documents match the classified fraud type's category, "
            "with moderate topical relevance; confidence slightly increased."
        )
    elif avg_relevance >= 0.75:
        adjusted = base_confidence
        notes = (
            "Retrieved documents are highly relevant to the query but not "
            "clearly categorised under the classified fraud type; "
            "confidence unchanged."
        )
    else:
        adjusted = max(0, base_confidence - 20)
        notes = (
            "Retrieved documents are only weakly relevant and do not match "
            "the classified fraud type's category; confidence reduced."
        )

    return ValidationResult(
        adjusted_confidence=adjusted,
        validation_notes=notes,
        category_match_ratio=round(category_match_ratio, 4),
    )

# ## 9. Module 6 - Rule-based Risk Engine


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

_INDICATOR_WEIGHTS: Dict[str, int] = {
    "Government Impersonation": 25,
    "Threat Language": 20,
    "Urgency": 15,
    "Urgent Payment Request": 15,
    "Money Demand": 30,
    "Isolation Tactics": 10,
    "Criminal Allegation": 20,
    "Suspicious Link": 10,
    "OTP Request": 20,
    "Blackmail / Extortion Threat": 25,
}
_DEFAULT_INDICATOR_WEIGHT = 8

def _severity_from_score(score: int) -> Severity:
    if score <= CONFIG.RISK_LOW_MAX:
        return Severity.LOW
    if score <= CONFIG.RISK_MEDIUM_MAX:
        return Severity.MEDIUM
    if score <= CONFIG.RISK_HIGH_MAX:
        return Severity.HIGH
    return Severity.CRITICAL

def compute_risk_score(normalized_indicators: List[str]) -> Dict[str, Any]:
    """
    Module 6 entry point.

    Deterministic rule-based scoring: sums fixed weights per normalised
    indicator (capped at 100) and maps the total onto a Severity band.
    """
    breakdown: Dict[str, int] = {}
    total = 0
    for indicator in normalized_indicators:
        weight = _INDICATOR_WEIGHTS.get(indicator, _DEFAULT_INDICATOR_WEIGHT)
        breakdown[indicator] = weight
        total += weight

    risk_score = min(100, total)
    severity = _severity_from_score(risk_score)

    logger.info(
        "Risk scoring complete. risk_score=%d severity=%s", risk_score, severity.value
    )
    return {
        "risk_score": risk_score,
        "severity": severity.value,
        "breakdown": breakdown,
    }

# ## 10. Full Pipeline Orchestration


def analyze_case(user_input: str) -> Dict[str, Any]:
    """
    Full Notebook 2 pipeline entry point.
    """
    case_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        signals = extract_signals(user_input)
        retrieved_chunks = retrieve_evidence(user_input, top_k=CONFIG.TOP_K)

        # === ACTUAL LLM CALL (walks CONFIG.OPENROUTER_MODEL_CANDIDATES) ===
        llm_output = run_llm_reasoning(user_input, signals, retrieved_chunks)
        # ====================================================================

        normalized_indicators = normalize_indicators(
            llm_output.get("indicators", [])
        )
        classification = classify_fraud_type(normalized_indicators)
        validation = validate_evidence(llm_output, classification, retrieved_chunks)
        risk = compute_risk_score(normalized_indicators)

        result = {
            "case_id": case_id,
            "timestamp": timestamp,
            "fraud_type": classification["fraud_type"],
            "classification_match_ratio": classification["match_ratio"],
            "confidence": validation.adjusted_confidence,
            "severity": risk["severity"],
            "risk_score": risk["risk_score"],
            "risk_breakdown": risk["breakdown"],
            "indicators": normalized_indicators,
            "entities": signals.entities,
            "behavioural_signals": {
                k: v for k, v in signals.behaviours.items() if v
            },
            "retrieved_documents": [
                {
                    "source": c.source_document,
                    "category": c.category,
                    "relevance_score": c.relevance_score,
                }
                for c in retrieved_chunks
            ],
            "evidence_sufficient": llm_output.get("evidence_sufficient", False),
            "category_match_ratio": validation.category_match_ratio,
            "validation_notes": validation.validation_notes,
            "summary": llm_output.get("explanation", ""),
            "model_used": llm_output.get("_model_used", "unknown"),
        }

        logger.info(
            "Case %s analysed. fraud_type=%s severity=%s confidence=%d model=%s",
            case_id,
            result["fraud_type"],
            result["severity"],
            result["confidence"],
            result["model_used"],
        )
        return result

    except Exception as exc:
        logger.exception("Failed to analyse case %s", case_id)
        raise FraudIntelligenceError(
            f"Pipeline failed for case {case_id}: {exc}"
        ) from exc

# ## 11. Test Cases
#
# Before running this section, set your OpenRouter API key, for example
# in a previous cell:
#
# ```python
# import os
# os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-..."
# ```
#
# Never hardcode the key directly in a committed notebook cell.
#
# This entire section only executes when this file is run directly
# (`python fraud_intelligence_engine.py`), never on a plain
# `import fraud_intelligence_engine`. This prevents every importer of this
# module (including Notebook 8's orchestrator) from silently triggering
# real OpenRouter API calls on every single import.


SAMPLE_CASES = [
    (
        "digital_arrest_case",
        "Hello Sir, I am from CBI. Your Aadhaar is linked with money "
        "laundering. Do not disconnect the call. Transfer Rs 2,00,000 "
        "immediately to avoid arrest.",
    ),
    (
        "benign_case",
        "Hi, just checking if you are free for lunch tomorrow at 1pm.",
    ),
]


def _run_sample_cases() -> Dict[str, Any]:
    """Runs the two SAMPLE_CASES through analyze_case() and prints each result."""
    test_results: Dict[str, Any] = {}
    for case_name, case_text in SAMPLE_CASES:
        try:
            test_results[case_name] = analyze_case(case_text)
        except FraudIntelligenceError as exc:
            logger.error("Test case '%s' failed: %s", case_name, exc)
            test_results[case_name] = {"error": str(exc)}

    for case_name, output in test_results.items():
        print(f"--- {case_name} ---")
        print(json.dumps(output, indent=2, default=str))
        print()

    return test_results

# ## 12. Notes and Limitations
#
# - FIX-2026-07-22: `FraudIntelligenceError` is now actually defined
#   (previously referenced but never declared anywhere in the file, which
#   masked the real OpenRouter 404 behind a NameError in the orchestrator's
#   fallback path).
# - FIX-2026-07-22: replaced the single hardcoded OpenRouter model with an
#   ordered `CONFIG.OPENROUTER_MODEL_CANDIDATES` list. `run_llm_reasoning`
#   walks the list and only advances to the next model on a 404
#   ("no endpoints found") - any other error (auth, malformed response,
#   non-recoverable JSON failure) still surfaces immediately. Free-tier
#   model IDs on OpenRouter rotate without notice, so treat this list as
#   something to periodically check against https://openrouter.ai/models
#   rather than a fixed constant.
# - SECURITY FIX (2026-07-10): removed a hardcoded real API key that was
#   previously embedded directly in the config. That key must be rotated
#   on openrouter.ai - treat it as already leaked. The key now must come
#   from the `OPENROUTER_API_KEY` environment variable, with a loud
#   failure if unset.
# - FIXED (2026-07-10): JSON truncation crash - hidden reasoning tokens were
#   consuming most of `max_tokens`, cutting the final JSON off mid-string.
#   Fixed by (a) capping reasoning tokens separately via
#   `reasoning.max_tokens`, (b) raising the overall `max_tokens` budget,
#   (c) detecting `finish_reason == "length"` and retrying once with a
#   larger budget, and (d) a heuristic repair pass as a last resort so a
#   partially truncated answer still produces a usable (flagged) result
#   instead of crashing the whole case.
# - FIXED (2026-07-11): `"response_format": {"type": "json_object"}` was
#   briefly added to force valid JSON, but some providers reject that
#   format with a 400. Removed - the system prompt instruction plus the
#   parse/repair pipeline already gets valid JSON reliably without it.
# - FIXED: L2 distance to similarity conversion - uses `1/(1+distance)`.
# - FIXED: response shape handling for reasoning-model `reasoning_details`.
# - FIXED: sections 11/13 are gated behind `if __name__ == "__main__":` so
#   importing this module (e.g. from Notebook 8's orchestrator) never
#   triggers live API calls or prints test output.
# - Removed the ad-hoc debug print block that was in `analyze_case()`
#   (the "=== DEBUG BEFORE LLM CALL ===" prints) - it added noise to every
#   real orchestrator run and duplicated what the logger already records
#   at INFO level.
# - The fraud type signature table (Module 4) and indicator weight table
#   (Module 6) are starting points for the hackathon demo.
# - Indicator normalisation uses a fixed synonym list plus fuzzy matching.
# - This notebook produces intelligence only; action recommendations belong
#   in Notebook 3.
# - Regex-based entity extraction is intentionally simple for the MVP.


# ## 13. Deterministic Test Suite
#
# Originally provided as a separate script, `test_fraud_intelligence_engine.py`,
# meant to be run after importing everything above and after setting
# `os.environ["OPENROUTER_API_KEY"]`.
#
# This does NOT call any AI to grade itself - it is a plain deterministic
# comparator. Since Module 3 (LLM reasoning) is non-deterministic, indicator
# lists are compared as "expected indicators are a subset of what came back"
# rather than exact match - that is the realistic bar for a live LLM call.
#
# This section, including the call to run_test_suite() at the very bottom
# of the file, only executes under `if __name__ == "__main__":`.


# ---------------------------------------------------------------------------
# Test cases: (name, input_text, expected_dict)
#
# expected_dict fields:
#   fraud_type          - exact string match required
#   severity            - exact string match required
#   min_indicators      - normalized indicators must be a superset of this list
#   risk_score_min       - risk_score must be >= this value
#   risk_score_max       - risk_score must be <= this value (loose band, since
#                          LLM indicator picks vary run to run)
# ---------------------------------------------------------------------------

TEST_CASES = [
    (
        "digital_arrest_case",
        "Hello Sir, I am from CBI. Your Aadhaar is linked with money "
        "laundering. Do not disconnect the call. Transfer Rs 2,00,000 "
        "immediately to avoid arrest.",
        {
            "fraud_type": "Digital Arrest Scam",
            "severity": "High",
            "min_indicators": [
                "Government Impersonation",
                "Criminal Allegation",
            ],
            "risk_score_min": 60,
            "risk_score_max": 100,
        },
    ),
    (
        "benign_case",
        "Hi, just checking if you are free for lunch tomorrow at 1pm.",
        {
            "fraud_type": "Unclassified Suspicious Activity",
            "severity": "Low",
            "min_indicators": [],
            "risk_score_min": 0,
            "risk_score_max": 0,
        },
    ),
    (
        "upi_payment_fraud_case",
        "You have received Rs 5,000 by mistake via UPI. Please transfer it "
        "back immediately to this UPI ID rahul.verify@upi or we will report "
        "you to the bank. Share the OTP sent to your phone to confirm the "
        "reversal right now.",
        {
            "fraud_type": "UPI / Payment Fraud",
            "severity": None,
            "min_indicators": ["OTP Request"],
            "risk_score_min": 20,
            "risk_score_max": 100,
        },
    ),
    (
        "phishing_credential_case",
        "Your bank account will be suspended. Verify immediately by "
        "clicking this link: http://secure-bank-verify.example.com and "
        "entering your OTP to keep your account active.",
        {
            "fraud_type": "Phishing / Credential Theft",
            "severity": None,
            "min_indicators": ["Suspicious Link", "OTP Request"],
            "risk_score_min": 20,
            "risk_score_max": 100,
        },
    ),
    (
        "extortion_threat_case",
        "We have obtained your private photos. Pay Rs 50,000 immediately "
        "or we will leak everything online and you will face a criminal "
        "case and non bailable arrest.",
        {
            "fraud_type": "Extortion / Threat-based Fraud",
            "severity": None,
            "min_indicators": ["Threat Language"],
            "risk_score_min": 30,
            "risk_score_max": 100,
        },
    ),
    (
        "ambiguous_weak_signal_case",
        "This is urgent, please call me back as soon as you can, it's "
        "important.",
        {
            "fraud_type": "Unclassified Suspicious Activity",
            "severity": None,
            "min_indicators": [],
            "risk_score_min": 0,
            "risk_score_max": 30,
        },
    ),
]

def _check_field(label: str, actual: Any, expected: Any) -> bool:
    if expected is None:
        return True  # not asserted for this case
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    print(f"    [{status}] {label}: expected={expected!r} actual={actual!r}")
    return ok

def _check_min_indicators(actual_indicators: List[str], expected_min: List[str]) -> bool:
    actual_set = set(actual_indicators)
    missing = [ind for ind in expected_min if ind not in actual_set]
    ok = not missing
    status = "PASS" if ok else "FAIL"
    print(
        f"    [{status}] min_indicators: expected subset={expected_min!r} "
        f"actual={actual_indicators!r}"
        + (f" MISSING={missing!r}" if missing else "")
    )
    return ok

def _check_range(label: str, actual: int, lo: int, hi: int) -> bool:
    ok = lo <= actual <= hi
    status = "PASS" if ok else "FAIL"
    print(f"    [{status}] {label}: expected in [{lo},{hi}] actual={actual}")
    return ok

def run_test_suite() -> Dict[str, Any]:
    """
    Runs every case in TEST_CASES through analyze_case() and compares the
    result against its expected_dict. Prints a PASS/FAIL breakdown per
    field per case, then a final summary line.
    """
    total_checks = 0
    passed_checks = 0
    case_results: Dict[str, Any] = {}

    for name, text, expected in TEST_CASES:
        print(f"\n=== {name} ===")
        print(f"Input: {text[:80]}{'...' if len(text) > 80 else ''}")

        try:
            result = analyze_case(text)
        except FraudIntelligenceError as exc:
            print(f"    [FAIL] analyze_case raised an error: {exc}")
            case_results[name] = {"error": str(exc)}
            total_checks += 1
            continue

        case_results[name] = result
        checks: List[bool] = []

        checks.append(
            _check_field("fraud_type", result["fraud_type"], expected["fraud_type"])
        )
        checks.append(
            _check_field("severity", result["severity"], expected["severity"])
        )
        checks.append(
            _check_min_indicators(result["indicators"], expected["min_indicators"])
        )
        checks.append(
            _check_range(
                "risk_score",
                result["risk_score"],
                expected["risk_score_min"],
                expected["risk_score_max"],
            )
        )

        total_checks += len(checks)
        passed_checks += sum(checks)

        print(f"    confidence={result['confidence']} "
              f"classification_match_ratio={result['classification_match_ratio']} "
              f"model_used={result.get('model_used')}")

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed_checks}/{total_checks} checks passed "
          f"across {len(TEST_CASES)} cases")
    print("=" * 60)

    return case_results


# ============================================================================
# Entry point - EVERYTHING below only runs when this file is executed
# directly (`python fraud_intelligence_engine.py`), never on plain import.
# ============================================================================

if __name__ == "__main__":
    print("=== Running Section 11 sample cases ===\n")
    _run_sample_cases()

    print("\n=== Running Section 13 deterministic test suite ===")
    all_results = run_test_suite()
    print("\nFull results (for inspection):")
    print(json.dumps(all_results, indent=2, default=str))