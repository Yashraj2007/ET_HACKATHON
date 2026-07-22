# Generated from: digital_public_safety_platform.ipynb
# Converted at: 2026-07-15T01:57:21.312Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# Generated from: digital_public_safety_platform.ipynb
# Converted at: 2026-07-15T01:35:05.787Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # Digital Public Safety Platform
# 
# **ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)**
# 
# **Notebook 8 - Master Orchestrator (Revision 4 - fixed dashboard ordering bug)**
# 
# This notebook is a direct, cell-by-cell conversion of `digital_public_safety_platform.py`. No code or comments have been changed; the original file has only been split into notebook cells along its existing numbered section headers, with a short markdown heading added before each section for readability.


# digital_public_safety_platform.py
# ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)
# Notebook 8 - Master Orchestrator (Revision 4 - fixed dashboard ordering bug)
#
# Mission (one sentence):
# Take a single citizen-reported case from intake to a merged, multi-
# audience intelligence package by calling every specialized engine
# (Notebooks 2-7) in the right order, fusing their outputs into one
# threat score, validating them against each other, and assembling one
# Digital Public Safety Intelligence Package.
#
# REVISION 4 FIX (this revision):
# build_administrator_dashboard(master) reads master["audit_trail"],
# master["execution_statistics"], and master["engine_health"]. Revision 3
# called it together with the other dashboards BEFORE those three keys
# were populated on `master`, which raised:
#     KeyError: 'audit_trail'
# (and would have raised KeyError: 'execution_statistics' /
# KeyError: 'engine_health' right after, for the same reason).
#
# The fix: populate, in this exact order, right after the decision
# pipeline finishes and BEFORE any dashboard is built:
#   1. master["incident_timeline"]
#   2. master["audit_trail"]              (interim - stages so far)
#   3. master["execution_statistics"]     (interim total_seconds)
#   4. master["engine_health"]            (derived from audit_trail)
#   5. master["executive_summary"]
#   6. master["platform_dashboard_text"]
# ONLY THEN are the five audience dashboards built (citizen, police, bank,
# telecom, administrator) - all five can now safely read any of the keys
# above. After the final report is generated (which adds one more audit
# entry for its own stage), audit_trail/execution_statistics/engine_health
# are refreshed once more so the totals/health stored on the returned
# master package are fully accurate, exactly as Revision 2 already did
# for audit_trail/execution_statistics alone.
#
# What this notebook is NOT:
#   - It is not an AI reasoning engine. It performs no fraud
#     classification, no computer vision, no graph analytics, and no
#     geospatial clustering itself - it calls the notebooks that do.
#   - It is not a replacement for Notebooks 2-7. It depends on them.
#   - It does not store data long-term. The in-memory Case Registry here
#     exists only to let the network (Notebook 6) and geospatial
#     (Notebook 7) engines see prior cases within a single running
#     process; a production deployment would back this with a database.
#
# Design approach - engine adapters:
# Each of Notebooks 2-7 is treated as an independent module. This file
# tries to import the real module first; if that import fails, or if the
# real module raises at call time, it automatically falls back to a
# small, deterministic, clearly-labeled stand-in so the pipeline still
# runs end-to-end and every stage is honestly labeled "real_engine" or
# "stub_adapter" (or "stub_fallback_after_real_engine_error") in the
# audit trail. Nothing here re-implements fraud classification, network
# analytics, or geospatial clustering as a permanent design choice - the
# stand-ins exist only for graceful degradation.

import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("digital_public_safety_platform")

# ## 1. Engine Availability - import real Notebook 2-7 modules


# ============================================================================
# 1. Engine Availability - import real Notebook 2-7 modules
# ============================================================================
#
# Every notebook is imported the same way: try the real module first, and
# only fall back to a stand-in if the import itself fails. A second,
# independent fallback also exists at CALL time (see _run_stage and each
# adapter below) in case the real module imports fine but raises during
# execution (e.g. Notebook 2 needs OPENROUTER_API_KEY, Notebook 5 needs an
# actual image file on disk). Both fallback paths are logged so the audit
# trail never silently pretends a stub result came from a real engine.
#
# NOTE: the warnings you saw in your run ("fraud_intelligence_engine.py
# not found", etc.) are expected and harmless if those .py files are not
# sitting next to this file in the same working directory / on sys.path.
# The orchestrator is DESIGNED to keep working in that case (stub mode).
# To get "real_engine" instead of "stub_adapter" in the audit trail,
# place the actual notebook .py files (matching the import names below)
# in the same directory as this file, or on your PYTHONPATH.

try:
    import fraud_intelligence_engine as notebook2
    _NOTEBOOK2_AVAILABLE = True
except ImportError:
    notebook2 = None
    _NOTEBOOK2_AVAILABLE = False
    logger.warning("fraud_intelligence_engine.py not found; Notebook 2 will run in stub mode.")

try:
    import decision_intelligence_engine as notebook3
    _NOTEBOOK3_AVAILABLE = True
except ImportError:
    notebook3 = None
    _NOTEBOOK3_AVAILABLE = False
    logger.warning("decision_intelligence_engine.py not found; Notebook 3 will run in stub mode.")

try:
    import digital_evidence_intelligence_engine as notebook4
    _NOTEBOOK4_AVAILABLE = True
except ImportError:
    notebook4 = None
    _NOTEBOOK4_AVAILABLE = False
    logger.warning("digital_evidence_intelligence_engine.py not found; Notebook 4 will run in stub mode.")

try:
    import counterfeit_currency_intelligence_engine as notebook5
    _NOTEBOOK5_AVAILABLE = True
except ImportError:
    notebook5 = None
    _NOTEBOOK5_AVAILABLE = False
    logger.warning("counterfeit_currency_intelligence_engine.py not found; Notebook 5 will run in stub mode.")

try:
    import fraud_network_intelligence_engine as notebook6
    _NOTEBOOK6_AVAILABLE = True
except ImportError:
    notebook6 = None
    _NOTEBOOK6_AVAILABLE = False
    logger.warning("fraud_network_intelligence_engine.py not found; Notebook 6 will run in stub mode.")

try:
    import geospatial_crime_pattern_intelligence_engine as notebook7
    _NOTEBOOK7_AVAILABLE = True
except ImportError:
    notebook7 = None
    _NOTEBOOK7_AVAILABLE = False
    logger.warning("geospatial_crime_pattern_intelligence_engine.py not found; Notebook 7 will run in stub mode.")

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False


class EngineSource(str, Enum):
    '''Marks where a stage's output actually came from.'''
    REAL = "real_engine"
    STUB = "stub_adapter"
    STUB_FALLBACK = "stub_fallback_after_real_engine_error"
    SKIPPED = "skipped"

# ## 2. Configuration


# ============================================================================
# 2. Configuration
# ============================================================================


class Config:
    NOTEBOOK_VERSION = "v4.0"

    # --- Decision thresholds (stub Notebook 3 fallback only) ---
    DECISION_EMERGENCY_RISK_MIN = 90.0
    DECISION_URGENT_RISK_MIN = 70.0
    DECISION_HUMAN_REVIEW_RISK_MIN = 40.0

    # --- Fraud stub (fallback Notebook 2) ---
    FRAUD_KEYWORD_SCORE_CAP = 60.0
    FRAUD_BASE_SCORE = 20.0

    # --- Severity bands, shared by the fraud stub and the fusion engine
    # so severity labels stay consistent whether Notebook 2 or the stub
    # produced the underlying risk score. ---
    SEVERITY_LOW_MAX = 30
    SEVERITY_MEDIUM_MAX = 60
    SEVERITY_HIGH_MAX = 85

    # --- Counterfeit stub (fallback Notebook 5) ---
    COUNTERFEIT_SUSPICION_THRESHOLD = 0.55

    # --- Threat Fusion Engine weights (must sum to 1.0). Network-adjusted
    # risk gets the largest weight because it already folds in the
    # standalone fraud score plus corroborating network evidence. ---
    FUSION_WEIGHT_NETWORK_RISK = 0.45
    FUSION_WEIGHT_FRAUD_RISK = 0.20
    FUSION_WEIGHT_GEO_SIGNAL = 0.20
    FUSION_WEIGHT_COUNTERFEIT_SIGNAL = 0.15

    # --- Confidence Fusion weights (must sum to 1.0) ---
    CONFIDENCE_WEIGHT_FRAUD = 0.40
    CONFIDENCE_WEIGHT_NETWORK = 0.30
    CONFIDENCE_WEIGHT_GEO = 0.20
    CONFIDENCE_WEIGHT_COUNTERFEIT = 0.10

    # --- Hotspot / district priority -> numeric signal (0-100) used only
    # inside the Threat Fusion Engine, never shown to the user directly. ---
    PRIORITY_TO_SCORE = {"Critical": 95.0, "High": 75.0, "Medium": 50.0, "Low": 20.0}


CONFIG = Config()
assert abs(
    CONFIG.FUSION_WEIGHT_NETWORK_RISK + CONFIG.FUSION_WEIGHT_FRAUD_RISK
    + CONFIG.FUSION_WEIGHT_GEO_SIGNAL + CONFIG.FUSION_WEIGHT_COUNTERFEIT_SIGNAL - 1.0
) < 1e-6, "Threat fusion weights must sum to 1.0."
assert abs(
    CONFIG.CONFIDENCE_WEIGHT_FRAUD + CONFIG.CONFIDENCE_WEIGHT_NETWORK
    + CONFIG.CONFIDENCE_WEIGHT_GEO + CONFIG.CONFIDENCE_WEIGHT_COUNTERFEIT - 1.0
) < 1e-6, "Confidence fusion weights must sum to 1.0."

logger.info(
    "Notebook 8 configuration loaded. version=%s notebook2=%s notebook3=%s notebook4=%s notebook5=%s notebook6=%s notebook7=%s",
    CONFIG.NOTEBOOK_VERSION, _NOTEBOOK2_AVAILABLE, _NOTEBOOK3_AVAILABLE,
    _NOTEBOOK4_AVAILABLE, _NOTEBOOK5_AVAILABLE, _NOTEBOOK6_AVAILABLE, _NOTEBOOK7_AVAILABLE,
)


class OrchestrationError(Exception):
    '''Raised when Notebook 8 cannot produce a valid Digital Public Safety Intelligence Package.'''

# ## 3. Module 1 - Case Intake (input contract)


# ============================================================================
# 3. Module 1 - Case Intake (input contract)
# ============================================================================


@dataclass
class EvidenceItem:
    '''
    One piece of citizen-submitted evidence.

    evidence_type - a broad label such as "call_recording",
        "whatsapp_screenshot", "document", "currency_image", "text".
    content       - extractable text (a transcript, OCR text, a pasted
        message) where available, OR an image/document path when the
        real file lives on disk (see metadata["file_path"]).
    metadata      - anything evidence-type-specific: file_path,
        original_filename, source_channel, citizen_reported_suspicious,
        override_extracted_text (pre-computed OCR/ASR text from an
        upstream service), etc.
    '''
    evidence_type: str
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseIntake:
    case_id: str
    citizen_name: Optional[str] = None
    victim_id: Optional[str] = None
    timestamp: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    evidence: List[EvidenceItem] = field(default_factory=list)
    priority: str = "Normal"        # citizen/call-center-reported urgency; advisory only
    source: str = "citizen_app"
    amount_involved: float = 0.0


def intake_case(raw: CaseIntake) -> CaseIntake:
    '''Module 1 entry point. Validates minimum required fields and fills sensible defaults.'''
    if not raw.case_id:
        raise OrchestrationError("CaseIntake is missing a case_id; cannot proceed.")
    if not raw.timestamp:
        raw.timestamp = datetime.now(timezone.utc).isoformat()
    if not raw.victim_id:
        raw.victim_id = f"VICTIM-{raw.case_id}"
    logger.info("Case intake complete. case_id=%s evidence_items=%d", raw.case_id, len(raw.evidence))
    return raw

# ## 4. Module 9 - Case Registry (shared, in-memory, across process_case calls)


# ============================================================================
# 4. Module 9 - Case Registry (shared, in-memory, across process_case calls)
# ============================================================================
#
# A single, explicit registry that Notebooks 6 and 7 both read from, so
# the network and geospatial engines see every case processed so far in
# this running instance, not just the one currently in flight. A
# production deployment backs this with a real database; this in-memory
# version exists purely so a single demo/test process can show growing
# network and geographic intelligence across sequential cases.


class CaseRegistry:
    def __init__(self) -> None:
        self.network_cases: Dict[str, Any] = {}     # case_id -> notebook6.CaseRecord
        self.geo_cases: Dict[str, Any] = {}          # case_id -> notebook7.GeoCaseRecord
        self.master_packages: Dict[str, Dict[str, Any]] = {}   # case_id -> final master package

    def register_network_case(self, case_id: str, record: Any) -> None:
        self.network_cases[case_id] = record

    def register_geo_case(self, case_id: str, record: Any) -> None:
        self.geo_cases[case_id] = record

    def register_master_package(self, case_id: str, package: Dict[str, Any]) -> None:
        self.master_packages[case_id] = package

    def all_network_cases(self) -> List[Any]:
        return list(self.network_cases.values())

    def all_geo_cases(self) -> List[Any]:
        return list(self.geo_cases.values())

    def total_cases(self) -> int:
        return len(self.master_packages)


CASE_REGISTRY = CaseRegistry()

# ## 5. Module 2 - Evidence Router (smarter, per-entity routing)


# ============================================================================
# 5. Module 2 - Evidence Router (smarter, per-entity routing)
# ============================================================================


def route_evidence(case: CaseIntake) -> Dict[str, Any]:
    '''
    Module 2 entry point. Decides which downstream engines need to run
    and WHY, so the routing decision itself is explainable rather than a
    bare set of booleans.
    '''
    types_present = {item.evidence_type for item in case.evidence}
    has_location = case.city is not None or (case.latitude is not None and case.longitude is not None)

    reasons: List[str] = []
    plan = {
        "run_evidence_engine": True,
        "run_fraud_intelligence": True,
        "run_counterfeit_check": "currency_image" in types_present,
        "run_network_intelligence": True,
        "run_geospatial_intelligence": has_location,
        "run_decision_engine": True,
    }

    reasons.append("Evidence engine always runs to normalize whatever evidence was submitted.")
    reasons.append("Fraud intelligence always runs to classify the case.")
    if plan["run_counterfeit_check"]:
        reasons.append("Currency image evidence detected; routing to the Counterfeit Currency Engine.")
    else:
        reasons.append("No currency image evidence present; Counterfeit Currency Engine skipped.")
    reasons.append("Network intelligence always runs so this case joins the shared fraud graph.")
    if plan["run_geospatial_intelligence"]:
        reasons.append("City or GPS coordinates present; routing to the Geospatial Intelligence Engine.")
    else:
        reasons.append("No location data present; Geospatial Intelligence Engine skipped for this case.")
    reasons.append("Decision engine always runs to produce the final stakeholder actions.")

    plan["reasons"] = reasons
    logger.info("Evidence routing complete. case_id=%s plan=%s", case.case_id, {k: v for k, v in plan.items() if k != "reasons"})
    return plan

# ## 6. Module 3 - Run Evidence Engine (real Notebook 4 call, stub fallback)


# ============================================================================
# 6. Module 3 - Run Evidence Engine (real Notebook 4 call, stub fallback)
# ============================================================================

_ENTITY_PATTERNS: Dict[str, re.Pattern] = {
    "phone_numbers": re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b"),
    "upi_ids": re.compile(r"\b[\w.\-]{2,}@[a-zA-Z]{2,}\b"),
    "emails": re.compile(r"\b[\w.\-]+@[\w\-]+\.[a-zA-Z]{2,}\b"),
    "bank_accounts": re.compile(r"\b\d{9,18}\b"),
    "urls": re.compile(r"https?://[^\s]+"),
}


def _extract_entities_from_text_stub(text: str) -> Dict[str, List[str]]:
    '''Fallback-only regex entity extraction, used when Notebook 4 is unavailable or errors.'''
    entities: Dict[str, List[str]] = defaultdict(list)
    for entity_type, pattern in _ENTITY_PATTERNS.items():
        for match in pattern.findall(text):
            if match not in entities[entity_type]:
                entities[entity_type].append(match)
    entities["emails"] = [e for e in entities["emails"] if "." in e.split("@", 1)[-1]]
    entities["upi_ids"] = [u for u in entities["upi_ids"] if u not in entities["emails"]]
    return dict(entities)


def _to_notebook4_inputs(case: CaseIntake) -> List[Any]:
    '''Converts our EvidenceItem list into Notebook 4's EvidenceInput contract.'''
    inputs = []
    for item in case.evidence:
        file_path = item.metadata.get("file_path")
        inputs.append(notebook4.EvidenceInput(
            file_path=file_path,
            raw_text=item.content if not file_path else None,
            source_channel=item.metadata.get("source_channel", item.evidence_type),
            submitted_at=item.metadata.get("submitted_at", case.timestamp),
            original_filename=item.metadata.get("original_filename"),
            override_extracted_text=item.metadata.get("override_extracted_text"),
        ))
    return inputs


def run_evidence_engine(case: CaseIntake) -> Dict[str, Any]:
    '''Module 3 entry point (Notebook 4 adapter, real-first with stub fallback).'''
    if _NOTEBOOK4_AVAILABLE:
        try:
            inputs = _to_notebook4_inputs(case)
            package = notebook4.package_case_evidence(inputs, case_id=case.case_id)
            package["engine_source"] = EngineSource.REAL.value
            return package
        except Exception as exc:
            logger.warning("Notebook 4 raised at call time; falling back to stub evidence extraction. error=%s", exc)

    combined_text = " ".join(item.content for item in case.evidence if item.content)
    entities = _extract_entities_from_text_stub(combined_text)
    evidence_types_seen = sorted({item.evidence_type for item in case.evidence})

    return {
        "case_id": case.case_id,
        "engine_source": EngineSource.STUB.value if not _NOTEBOOK4_AVAILABLE else EngineSource.STUB_FALLBACK.value,
        "evidence_types_seen": evidence_types_seen,
        "metadata": entities,               # aligned with Notebook 4's top-level "metadata" key name
        "extracted_entities": entities,      # kept for backward-compatible readers
        "text": combined_text,
        "evidence_quality": "Unknown",
        "evidence_summary": combined_text[:280] + ("..." if len(combined_text) > 280 else ""),
    }

# ## 7. Module 4 - Run Fraud Intelligence (real Notebook 2 call, stub fallback)


# ============================================================================
# 7. Module 4 - Run Fraud Intelligence (real Notebook 2 call, stub fallback)
# ============================================================================

_FRAUD_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "Digital Arrest Scam": ["digital arrest", "rbi", "cbi", "arrest warrant", "video call", "police officer", "customs"],
    "UPI / Payment Fraud": ["upi", "refund", "cashback", "wrong transaction", "collect request"],
    "Romance Scam": ["love", "relationship", "gift", "customs duty", "dating"],
    "Job Scam": ["job offer", "work from home", "registration fee", "part time job", "recruiter"],
    "Lottery Scam": ["lottery", "prize", "winner", "claim your", "lucky draw"],
    "Investment Scam": ["investment", "guaranteed return", "trading tips", "stock tips", "crypto"],
}


def _severity_from_risk(risk_score: float) -> str:
    '''Shared severity banding, kept consistent with Notebook 2's own bands.'''
    if risk_score <= CONFIG.SEVERITY_LOW_MAX:
        return "Low"
    if risk_score <= CONFIG.SEVERITY_MEDIUM_MAX:
        return "Medium"
    if risk_score <= CONFIG.SEVERITY_HIGH_MAX:
        return "High"
    return "Critical"


def _fraud_stub(case: CaseIntake, evidence_package: Dict[str, Any]) -> Dict[str, Any]:
    '''Deterministic, keyword-weighted fallback classifier used only when Notebook 2 is unavailable or errors.'''
    text = (evidence_package.get("text") or " ".join(item.content for item in case.evidence if item.content)).lower()

    scores: Dict[str, int] = {}
    matched_keywords: Dict[str, List[str]] = {}
    for fraud_type, keywords in _FRAUD_TYPE_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if hits:
            scores[fraud_type] = len(hits)
            matched_keywords[fraud_type] = hits

    if scores:
        fraud_type = max(scores, key=scores.get)
        keyword_component = min(CONFIG.FRAUD_KEYWORD_SCORE_CAP, scores[fraud_type] * 15.0)
        reasoning = [f"Matched signal keywords for '{fraud_type}': {', '.join(matched_keywords[fraud_type])}."]
    else:
        fraud_type = "Unclassified Suspicious Activity"
        keyword_component = 0.0
        reasoning = ["No known fraud-pattern keywords were matched in the submitted evidence text."]

    entities = evidence_package.get("metadata") or evidence_package.get("extracted_entities") or {}
    entity_count = sum(len(v) for v in entities.values() if isinstance(v, list))
    entity_component = min(15.0, entity_count * 2.0)
    if entity_count:
        reasoning.append(f"{entity_count} identifiable entity(ies) extracted from evidence.")

    amount_component = min(5.0, case.amount_involved / 20000.0) if case.amount_involved else 0.0
    if case.amount_involved:
        reasoning.append(f"Amount involved: Rs {case.amount_involved:,.0f}.")

    risk_score = round(min(100.0, CONFIG.FRAUD_BASE_SCORE + keyword_component + entity_component + amount_component), 1)
    confidence = round(min(95.0, 40.0 + keyword_component + entity_component), 1)

    return {
        "case_id": case.case_id,
        "timestamp": case.timestamp,
        "engine_source": EngineSource.STUB.value if not _NOTEBOOK2_AVAILABLE else EngineSource.STUB_FALLBACK.value,
        "fraud_type": fraud_type,
        "risk_score": risk_score,
        "confidence": confidence,
        "severity": _severity_from_risk(risk_score),
        "indicators": [],
        "entities": entities,
        "citations": {},
        "reasoning": reasoning,
        "summary": reasoning[0] if reasoning else "",
        "matched_keywords": matched_keywords,
    }


def run_fraud_intelligence(case: CaseIntake, evidence_package: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 4 entry point (Notebook 2 adapter, real-first with stub fallback).'''
    if _NOTEBOOK2_AVAILABLE:
        try:
            combined_text = evidence_package.get("text") or " ".join(item.content for item in case.evidence if item.content)
            result = notebook2.analyze_case(combined_text)
            result["engine_source"] = EngineSource.REAL.value
            result.setdefault("reasoning", [result.get("summary", "")])
            return result
        except Exception as exc:
            logger.warning("Notebook 2 raised at call time (likely missing OPENROUTER_API_KEY or no network); "
                            "falling back to stub fraud classification. error=%s", exc)

    return _fraud_stub(case, evidence_package)

# ## 8. Module 5 - Counterfeit Check (real Notebook 5 call, stub fallback)


# ============================================================================
# 8. Module 5 - Counterfeit Check (real Notebook 5 call, stub fallback)
# ============================================================================


def _counterfeit_stub(currency_items: List[EvidenceItem]) -> Dict[str, Any]:
    '''Deterministic pseudo-scored fallback, used only when Notebook 5 is unavailable, errors, or no file is on disk.'''
    findings = []
    max_suspicion = 0.0
    for item in currency_items:
        digest_source = item.content or item.metadata.get("file_path", item.evidence_type)
        digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
        pseudo_score = (int(digest[:8], 16) % 1000) / 1000.0
        if item.metadata.get("citizen_reported_suspicious"):
            pseudo_score = min(1.0, pseudo_score + 0.25)
        max_suspicion = max(max_suspicion, pseudo_score)
        findings.append({
            "evidence_content": digest_source,
            "suspicion_score": round(pseudo_score, 3),
            "citizen_flagged": bool(item.metadata.get("citizen_reported_suspicious", False)),
        })

    verdict = "Likely Counterfeit" if max_suspicion >= CONFIG.COUNTERFEIT_SUSPICION_THRESHOLD else "Inconclusive - Needs Manual Review"

    return {
        "engine_source": EngineSource.STUB.value if not _NOTEBOOK5_AVAILABLE else EngineSource.STUB_FALLBACK.value,
        "items_checked": len(currency_items),
        "findings": findings,
        "max_suspicion_score": round(max_suspicion, 3),
        "verdict": verdict,
        "note": "Pseudo-scored stand-in; treat verdict as advisory only.",
    }


def run_counterfeit_check(case: CaseIntake) -> Optional[Dict[str, Any]]:
    '''Module 5 entry point (Notebook 5 adapter). Returns None if there is nothing to check.'''
    currency_items = [item for item in case.evidence if item.evidence_type == "currency_image"]
    if not currency_items:
        return None

    if _NOTEBOOK5_AVAILABLE:
        items_with_files = [item for item in currency_items if item.metadata.get("file_path")]
        if items_with_files:
            try:
                per_item_results = []
                max_counterfeit_prob = 0.0
                for item in items_with_files:
                    result = notebook5.analyze_currency_image(
                        item.metadata["file_path"],
                        denomination_hint=item.metadata.get("denomination_hint"),
                        known_serial_database=item.metadata.get("known_serial_database"),
                    )
                    per_item_results.append(result)
                    max_counterfeit_prob = max(max_counterfeit_prob, result["currency_analysis"]["counterfeit_probability"])

                verdict = "Likely Counterfeit" if max_counterfeit_prob >= CONFIG.COUNTERFEIT_SUSPICION_THRESHOLD else "Likely Genuine"
                return {
                    "engine_source": EngineSource.REAL.value,
                    "items_checked": len(per_item_results),
                    "per_item_results": per_item_results,
                    "max_suspicion_score": round(max_counterfeit_prob, 3),
                    "verdict": verdict,
                }
            except Exception as exc:
                logger.warning("Notebook 5 raised at call time; falling back to stub counterfeit check. error=%s", exc)

    return _counterfeit_stub(currency_items)

# ## 9. Module 6 - Run Network Intelligence (real Notebook 6 call)


# ============================================================================
# 9. Module 6 - Run Network Intelligence (real Notebook 6 call)
# ============================================================================


def _build_network_case_record(case: CaseIntake, evidence_package: Dict[str, Any], fraud_package: Dict[str, Any]) -> Any:
    entities = evidence_package.get("metadata") or evidence_package.get("extracted_entities") or {}
    return notebook6.CaseRecord(
        case_id=case.case_id,
        victim_id=case.victim_id,
        fraud_type=fraud_package.get("fraud_type"),
        risk_score=fraud_package.get("risk_score", 0.0),
        phone_numbers=entities.get("phone_numbers", []),
        upi_ids=entities.get("upi_ids", []),
        emails=entities.get("emails", []),
        bank_accounts=entities.get("bank_accounts", []),
        urls=entities.get("urls", []),
        organizations=entities.get("organizations", []),
        amount_involved=case.amount_involved,
        city=case.city,
        state=case.state,
        timestamp=case.timestamp,
    )


def run_network_intelligence(case: CaseIntake, evidence_package: Dict[str, Any], fraud_package: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 6 entry point (real Notebook 6 call, with a minimal stub fallback).'''
    if not _NOTEBOOK6_AVAILABLE:
        return {
            "engine_source": EngineSource.STUB.value,
            "connected_cases": [], "communities": [], "fraud_campaigns": [], "money_mule_accounts": [],
            "central_actor": None,
            "risk_propagation": {
                "original_risk": fraud_package.get("risk_score", 0.0),
                "network_adjusted_risk": fraud_package.get("risk_score", 0.0),
                "boost_applied": 0.0, "driving_entity": None,
                "reasons": ["Notebook 6 module not available; network-adjusted risk defaults to the standalone score."],
            },
            "note": "fraud_network_intelligence_engine.py was not importable.",
        }

    try:
        record = _build_network_case_record(case, evidence_package, fraud_package)
        CASE_REGISTRY.register_network_case(case.case_id, record)

        package = notebook6.analyze_fraud_network(
            CASE_REGISTRY.all_network_cases(),
            focus_case_id=case.case_id,
            save_visualization=True,
            generate_report=False,   # Notebook 8 produces its own single merged report
        )
        package["engine_source"] = EngineSource.REAL.value
        return package
    except Exception as exc:
        logger.warning("Notebook 6 raised at call time; falling back to stub network package. error=%s", exc)
        return {
            "engine_source": EngineSource.STUB_FALLBACK.value,
            "connected_cases": [], "communities": [], "fraud_campaigns": [], "money_mule_accounts": [],
            "central_actor": None,
            "risk_propagation": {
                "original_risk": fraud_package.get("risk_score", 0.0),
                "network_adjusted_risk": fraud_package.get("risk_score", 0.0),
                "boost_applied": 0.0, "driving_entity": None,
                "reasons": [f"Notebook 6 raised an error at call time ({exc}); defaulting to the standalone risk score."],
            },
        }

# ## 10. Module 7 - Run Geospatial Intelligence (real Notebook 7 call)


# ============================================================================
# 10. Module 7 - Run Geospatial Intelligence (real Notebook 7 call)
# ============================================================================


def _find_case_campaign_id(case_id: str, network_package: Dict[str, Any]) -> Optional[str]:
    for campaign in network_package.get("fraud_campaigns", []):
        if case_id in campaign.get("linked_cases", []):
            return campaign["campaign_id"]
    return None


def _find_case_community_id(case_id: str, network_package: Dict[str, Any]) -> Optional[str]:
    for community in network_package.get("communities", []):
        if case_id in community.get("connected_cases", []):
            return community["community_id"]
    return None


def _case_touches_mule_account(case_id: str, network_package: Dict[str, Any]) -> bool:
    return any(case_id in mule.get("connected_cases", []) for mule in network_package.get("money_mule_accounts", []))


def run_geospatial_intelligence(case: CaseIntake, fraud_package: Dict[str, Any], network_package: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 7 entry point (real Notebook 7 call, with a minimal stub fallback).'''
    if not _NOTEBOOK7_AVAILABLE:
        return {
            "engine_source": EngineSource.STUB.value,
            "hotspots": [], "district_risk": [], "predicted_hotspots": [], "campaign_spread": [],
            "resource_recommendations": [], "nearest_cyber_cells": [], "confidence": 0.0,
            "note": "geospatial_crime_pattern_intelligence_engine.py was not importable.",
        }

    try:
        network_adjusted_risk = network_package.get("risk_propagation", {}).get(
            "network_adjusted_risk", fraud_package.get("risk_score", 0.0)
        )

        record = notebook7.GeoCaseRecord(
            case_id=case.case_id,
            city=case.city,
            state=case.state,
            latitude=case.latitude,
            longitude=case.longitude,
            fraud_type=fraud_package.get("fraud_type"),
            risk_score=network_adjusted_risk,
            amount_involved=case.amount_involved,
            timestamp=case.timestamp,
            campaign_id=_find_case_campaign_id(case.case_id, network_package),
            community_id=_find_case_community_id(case.case_id, network_package),
            is_mule_location=_case_touches_mule_account(case.case_id, network_package),
        )
        CASE_REGISTRY.register_geo_case(case.case_id, record)

        package = notebook7.analyze_geospatial_intelligence(
            CASE_REGISTRY.all_geo_cases(),
            save_visualization=True,
            generate_report=False,   # Notebook 8 produces its own single merged report
        )
        package["engine_source"] = EngineSource.REAL.value
        return package
    except Exception as exc:
        logger.warning("Notebook 7 raised at call time; falling back to stub geospatial package. error=%s", exc)
        return {
            "engine_source": EngineSource.STUB_FALLBACK.value,
            "hotspots": [], "district_risk": [], "predicted_hotspots": [], "campaign_spread": [],
            "resource_recommendations": [], "nearest_cyber_cells": [], "confidence": 0.0,
        }

# ## 11. Threat Fusion Engine


# ============================================================================
# 11. Threat Fusion Engine
# ============================================================================


def _counterfeit_signal_score(counterfeit_package: Optional[Dict[str, Any]]) -> float:
    '''Converts the counterfeit package (real or stub) into a 0-100 threat signal. No evidence -> neutral 0.'''
    if not counterfeit_package:
        return 0.0
    return round(counterfeit_package.get("max_suspicion_score", 0.0) * 100, 1)


def _geo_signal_score(case_id: str, geo_package: Dict[str, Any]) -> float:
    '''
    Converts geospatial context into a 0-100 threat signal: the priority
    of any hotspot this case falls in, otherwise the priority of this
    case's district, otherwise a neutral 0.
    '''
    for hotspot in geo_package.get("hotspots", []):
        if case_id in hotspot.get("case_ids", []):
            return CONFIG.PRIORITY_TO_SCORE.get(hotspot["priority"], 0.0)
    for district in geo_package.get("district_risk", []):
        if case_id in district.get("case_ids", []):
            return CONFIG.PRIORITY_TO_SCORE.get(district["priority"], 0.0)
    return 0.0


def fuse_threat_score(
    case_id: str,
    fraud_package: Dict[str, Any],
    network_package: Dict[str, Any],
    geo_package: Dict[str, Any],
    counterfeit_package: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    '''
    Threat Fusion Engine. Blends four independent signals into one 0-100
    overall threat score, rather than trusting any single engine's number
    in isolation. Every component is reported alongside the final score
    so the fusion is auditable, not a black box.
    '''
    fraud_risk = fraud_package.get("risk_score", 0.0)
    network_risk = network_package.get("risk_propagation", {}).get("network_adjusted_risk", fraud_risk)
    geo_signal = _geo_signal_score(case_id, geo_package)
    counterfeit_signal = _counterfeit_signal_score(counterfeit_package)

    fused = (
        CONFIG.FUSION_WEIGHT_NETWORK_RISK * network_risk
        + CONFIG.FUSION_WEIGHT_FRAUD_RISK * fraud_risk
        + CONFIG.FUSION_WEIGHT_GEO_SIGNAL * geo_signal
        + CONFIG.FUSION_WEIGHT_COUNTERFEIT_SIGNAL * counterfeit_signal
    )
    fused = round(min(100.0, fused), 1)

    return {
        "overall_threat_score": fused,
        "severity": _severity_from_risk(fused),
        "components": {
            "fraud_standalone_risk": fraud_risk,
            "network_adjusted_risk": network_risk,
            "geospatial_signal": geo_signal,
            "counterfeit_signal": counterfeit_signal,
        },
        "weights": {
            "network_adjusted_risk": CONFIG.FUSION_WEIGHT_NETWORK_RISK,
            "fraud_standalone_risk": CONFIG.FUSION_WEIGHT_FRAUD_RISK,
            "geospatial_signal": CONFIG.FUSION_WEIGHT_GEO_SIGNAL,
            "counterfeit_signal": CONFIG.FUSION_WEIGHT_COUNTERFEIT_SIGNAL,
        },
    }

# ## 12. Confidence Fusion Engine


# ============================================================================
# 12. Confidence Fusion Engine
# ============================================================================


def fuse_confidence(
    fraud_package: Dict[str, Any],
    network_package: Dict[str, Any],
    geo_package: Dict[str, Any],
    counterfeit_package: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    '''
    Weighted confidence fusion. A component that produced no signal (e.g.
    no communities detected, no counterfeit evidence submitted) is
    excluded from the blend and the remaining weights are re-normalized,
    rather than silently treating "no signal" as "zero confidence".
    '''
    components: Dict[str, float] = {"fraud": fraud_package.get("confidence", 0.0)}
    weights: Dict[str, float] = {"fraud": CONFIG.CONFIDENCE_WEIGHT_FRAUD}

    communities = network_package.get("communities", [])
    if communities:
        components["network"] = communities[0].get("confidence", 0.0)
        weights["network"] = CONFIG.CONFIDENCE_WEIGHT_NETWORK

    if geo_package.get("confidence"):
        components["geospatial"] = geo_package["confidence"]
        weights["geospatial"] = CONFIG.CONFIDENCE_WEIGHT_GEO

    if counterfeit_package:
        certainty = abs(counterfeit_package.get("max_suspicion_score", 0.5) - 0.5) * 2 * 100
        components["counterfeit"] = round(certainty, 1)
        weights["counterfeit"] = CONFIG.CONFIDENCE_WEIGHT_COUNTERFEIT

    total_weight = sum(weights.values()) or 1.0
    fused = sum(components[k] * weights[k] for k in components) / total_weight

    return {
        "overall_confidence": round(min(99.0, fused), 1),
        "components": components,
        "weights_used": weights,
    }

# ## 13. Cross-Notebook Validation


# ============================================================================
# 13. Cross-Notebook Validation
# ============================================================================


def validate_cross_notebook_consistency(
    fraud_package: Dict[str, Any],
    network_package: Dict[str, Any],
    geo_package: Dict[str, Any],
) -> Dict[str, Any]:
    '''
    Compares Notebook 2's classified fraud_type against Notebook 6's
    dominant community fraud type and Notebook 7's dominant hotspot fraud
    type. A single engine disagreeing is common and not flagged (small
    samples vary); TWO OR MORE independent engines disagreeing with
    Notebook 2 is treated as a genuine conflict that should force human
    review rather than an automatic high-confidence decision.
    '''
    fraud_type = fraud_package.get("fraud_type")
    conflicts: List[str] = []

    communities = network_package.get("communities", [])
    if communities and communities[0].get("dominant_fraud") not in (None, "Unclassified", fraud_type):
        conflicts.append(
            f"Notebook 2 classified this case as '{fraud_type}', but the network community "
            f"it belongs to is dominated by '{communities[0]['dominant_fraud']}'."
        )

    hotspots = geo_package.get("hotspots", [])
    if hotspots and hotspots[0].get("dominant_fraud") not in (None, "Unclassified", fraud_type):
        conflicts.append(
            f"Notebook 2 classified this case as '{fraud_type}', but the geographic hotspot "
            f"it falls in is dominated by '{hotspots[0]['dominant_fraud']}'."
        )

    return {
        "is_consistent": len(conflicts) < 2,
        "conflicts_found": conflicts,
        "force_human_review": len(conflicts) >= 2,
    }

# ## 14. Module 8 - Final Decision (real Notebook 3 call, stub fallback)


# ============================================================================
# 14. Module 8 - Final Decision (real Notebook 3 call, stub fallback)
# ============================================================================


class DecisionCategory(str, Enum):
    EMERGENCY = "Emergency"
    URGENT_ACTION = "Urgent Action"
    NEEDS_HUMAN_REVIEW = "Needs Human Review"
    AWARENESS_ONLY = "Awareness Only"
    NO_ACTION = "No Action - Benign"


def _decision_stub(
    fraud_package: Dict[str, Any],
    counterfeit_package: Optional[Dict[str, Any]],
    fused_risk: float,
    validation: Dict[str, Any],
) -> Dict[str, Any]:
    '''Deterministic fallback decision policy, used only when Notebook 3 is unavailable or errors.'''
    reasons: List[str] = [f"Fused overall threat score is {fused_risk}."]

    if validation["force_human_review"]:
        category = DecisionCategory.NEEDS_HUMAN_REVIEW
        reasons.append("Cross-notebook validation found conflicting fraud-type signals; routed to human review.")
    elif fused_risk >= CONFIG.DECISION_EMERGENCY_RISK_MIN:
        category = DecisionCategory.EMERGENCY
    elif fused_risk >= CONFIG.DECISION_URGENT_RISK_MIN:
        category = DecisionCategory.URGENT_ACTION
    elif fused_risk >= CONFIG.DECISION_HUMAN_REVIEW_RISK_MIN:
        category = DecisionCategory.AWARENESS_ONLY
    else:
        category = DecisionCategory.NO_ACTION

    if counterfeit_package and counterfeit_package.get("verdict") == "Likely Counterfeit":
        reasons.append("Submitted currency evidence was flagged as likely counterfeit.")

    stakeholder_actions = {
        "citizen": [
            "File a formal complaint on cybercrime.gov.in if not already done.",
            "Do not make any further payments to the numbers/accounts involved.",
        ],
        "police": [], "bank": [], "telecom": [],
    }
    if category in (DecisionCategory.EMERGENCY, DecisionCategory.URGENT_ACTION):
        stakeholder_actions["police"].append("Prioritize investigation; cross-reference network and geospatial findings.")

    return {
        "engine_source": EngineSource.STUB.value if not _NOTEBOOK3_AVAILABLE else EngineSource.STUB_FALLBACK.value,
        "case_decision": category.value,
        "priority": category.value,
        "reasons": reasons,
        "citizen_actions": stakeholder_actions["citizen"],
        "police_actions": stakeholder_actions["police"],
        "bank_actions": stakeholder_actions["bank"],
        "telecom_actions": stakeholder_actions["telecom"],
    }


def run_decision_engine(
    fraud_package: Dict[str, Any],
    network_package: Dict[str, Any],
    counterfeit_package: Optional[Dict[str, Any]],
    fusion_result: Dict[str, Any],
    validation: Dict[str, Any],
) -> Dict[str, Any]:
    '''
    Module 8 entry point (Notebook 3 adapter). Feeds Notebook 3 the FUSED
    threat score and severity (not the raw Notebook-2 standalone numbers),
    so its policy engine reasons over the same number the rest of this
    package reports as the overall threat level.
    '''
    if _NOTEBOOK3_AVAILABLE:
        try:
            adjusted_input = dict(fraud_package)
            adjusted_input["risk_score"] = fusion_result["overall_threat_score"]
            adjusted_input["severity"] = fusion_result["severity"]

            similar_cases = [
                {"case_id": cid, "similarity": 0.75}
                for cid in network_package.get("connected_cases", [])
            ]

            result = notebook3.build_decision_package(adjusted_input, similar_cases=similar_cases or None)
            result["engine_source"] = EngineSource.REAL.value

            if validation["force_human_review"] and result.get("case_decision") != notebook3.CaseDecision.NEEDS_HUMAN_REVIEW.value:
                result["case_decision"] = notebook3.CaseDecision.NEEDS_HUMAN_REVIEW.value
                result.setdefault("policy_reasons", []).append(
                    "Overridden by Notebook 8: cross-notebook validation found conflicting fraud-type signals."
                )
            return result
        except Exception as exc:
            logger.warning("Notebook 3 raised at call time; falling back to stub decision policy. error=%s", exc)

    return _decision_stub(fraud_package, counterfeit_package, fusion_result["overall_threat_score"], validation)


def _decision_category_label(decision_package: Dict[str, Any]) -> str:
    '''Normalizes whichever key the real Notebook 3 or the stub used for the final category.'''
    return decision_package.get("case_decision") or decision_package.get("decision_category") or "Unknown"


def _decision_reasons(decision_package: Dict[str, Any]) -> List[str]:
    return decision_package.get("policy_reasons") or decision_package.get("reasons") or []


def _stakeholder_actions(decision_package: Dict[str, Any], stakeholder: str) -> List[str]:
    '''Normalizes stakeholder action lookup across the real Notebook 3 shape and the stub shape.'''
    direct_key = f"{stakeholder}_actions"
    if direct_key in decision_package:
        return decision_package[direct_key]
    return decision_package.get("stakeholder_actions", {}).get(stakeholder, [])

# ## 15. Explainability Chain


# ============================================================================
# 15. Explainability Chain
# ============================================================================


def build_explainability(
    fraud_package: Dict[str, Any],
    network_package: Dict[str, Any],
    geo_package: Dict[str, Any],
    fusion_result: Dict[str, Any],
    validation: Dict[str, Any],
    decision_package: Dict[str, Any],
) -> List[Dict[str, str]]:
    '''Module 16 entry point. A short, ordered "why" chain a reviewer can read in one glance.'''
    chain: List[Dict[str, str]] = []
    chain.append({"step": "Fraud type identified", "detail": fraud_package.get("fraud_type", "Unclassified")})
    for reason in fraud_package.get("reasoning", []):
        chain.append({"step": "Evidence signal", "detail": reason})

    risk_info = network_package.get("risk_propagation", {})
    if risk_info.get("boost_applied", 0) > 0:
        chain.append({
            "step": "Network context raised risk",
            "detail": f"{risk_info['original_risk']} -> {risk_info['network_adjusted_risk']} (driven by {risk_info.get('driving_entity')})",
        })

    hotspots = geo_package.get("hotspots", [])
    if hotspots:
        chain.append({
            "step": "Geographic context",
            "detail": f"Case falls within hotspot {hotspots[0]['hotspot_id']} ({hotspots[0]['primary_city']}), priority {hotspots[0]['priority']}.",
        })

    chain.append({
        "step": "Threat fusion",
        "detail": f"Overall threat score {fusion_result['overall_threat_score']} ({fusion_result['severity']}), "
                  f"blended from fraud/network/geo/counterfeit signals.",
    })

    if validation["conflicts_found"]:
        for conflict in validation["conflicts_found"]:
            chain.append({"step": "Validation conflict", "detail": conflict})

    for reason in _decision_reasons(decision_package):
        chain.append({"step": "Decision factor", "detail": reason})

    chain.append({"step": "Final decision", "detail": _decision_category_label(decision_package)})
    return chain

# ## 16. Incident Timeline


# ============================================================================
# 16. Incident Timeline
# ============================================================================


def build_incident_timeline(
    case: CaseIntake,
    evidence_package: Dict[str, Any],
    fraud_package: Dict[str, Any],
    network_package: Dict[str, Any],
    geo_package: Dict[str, Any],
    decision_package: Dict[str, Any],
) -> List[Dict[str, str]]:
    '''
    Reconstructs a plain-language, chronological view of how this case
    moved through the platform - useful for an investigator or auditor to
    see when each stage fired.
    '''
    timeline: List[Dict[str, str]] = []
    base_time = case.timestamp or datetime.now(timezone.utc).isoformat()

    timeline.append({"event": f"Case {case.case_id} received via {case.source}.", "timestamp": base_time})
    timeline.append({"event": f"Evidence normalized ({len(case.evidence)} item(s)).", "timestamp": base_time})
    timeline.append({
        "event": f"Fraud classified as '{fraud_package.get('fraud_type')}' "
                 f"(standalone risk {fraud_package.get('risk_score')}).",
        "timestamp": base_time,
    })

    if network_package.get("connected_cases"):
        timeline.append({
            "event": f"Matched to {len(network_package['connected_cases'])} prior case(s) in the fraud network.",
            "timestamp": base_time,
        })
    if network_package.get("money_mule_accounts"):
        timeline.append({"event": "Linked account(s) flagged as likely money mule.", "timestamp": base_time})

    if geo_package.get("hotspots"):
        for hotspot in geo_package["hotspots"]:
            if case.case_id in hotspot.get("case_ids", []):
                timeline.append({"event": f"Case falls within geographic hotspot {hotspot['hotspot_id']}.", "timestamp": base_time})
                break

    timeline.append({
        "event": f"Final decision: {_decision_category_label(decision_package)}.",
        "timestamp": base_time,
    })
    return timeline

# ## 17. Engine Health Dashboard


# ============================================================================
# 17. Engine Health Dashboard
# ============================================================================


def build_engine_health(audit_trail: List[Dict[str, Any]]) -> Dict[str, Any]:
    '''
    One place to see, per pipeline stage, whether the real engine ran, a
    stub ran by design, or a stub ran because the real engine failed at
    call time - the last case is the one worth watching in a live
    deployment.
    '''
    health: Dict[str, Any] = {}
    for entry in audit_trail:
        stage = entry["stage"]
        source = entry.get("engine_source", EngineSource.SKIPPED.value)
        if source == EngineSource.REAL.value:
            status = "Healthy (real engine)"
        elif source == EngineSource.STUB.value:
            status = "Stub by design (module not installed / not applicable)"
        elif source == EngineSource.STUB_FALLBACK.value:
            status = "DEGRADED - real engine failed at runtime, stub fallback used"
        else:
            status = "Skipped"
        health[stage] = {"status": status, "engine_source": source, "duration_ms": entry.get("duration_ms")}
    return health

# ## 18. Modules 10-14 - Audience-Specific Dashboards


# ============================================================================
# 18. Modules 10-14 - Audience-Specific Dashboards
# ============================================================================


def _risk_band(score: float) -> str:
    if score >= CONFIG.DECISION_EMERGENCY_RISK_MIN:
        return "Critical"
    if score >= CONFIG.DECISION_URGENT_RISK_MIN:
        return "High"
    if score >= CONFIG.DECISION_HUMAN_REVIEW_RISK_MIN:
        return "Medium"
    return "Low"


def build_citizen_dashboard(master: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 11 entry point. Citizens see outcomes and guidance, not investigative internals.'''
    fraud = master["fraud_intelligence"]
    decision = master["decision_intelligence"]
    return {
        "case_id": master["case"]["case_id"],
        "fraud_type": fraud.get("fraud_type"),
        "risk_level": _risk_band(master["overall_threat_level"]),
        "what_this_means": _decision_category_label(decision),
        "recommended_actions": _stakeholder_actions(decision, "citizen"),
        "national_cyber_crime_helpline": "1930",
        "national_cyber_crime_portal": "cybercrime.gov.in",
        "safety_advice": [
            "Do not share OTPs, passwords, or remote-access app codes with anyone.",
            "Government agencies do not conduct arrests or investigations over video call.",
            "When in doubt, hang up and call the organization back using an officially published number.",
        ],
    }


def build_police_dashboard(master: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 12 entry point. Police get the full investigative picture.'''
    return {
        "case_id": master["case"]["case_id"],
        "fraud_intelligence": master["fraud_intelligence"],
        "fraud_network_intelligence": master["fraud_network_intelligence"],
        "geospatial_intelligence": master["geospatial_intelligence"],
        "counterfeit_intelligence": master["counterfeit_intelligence"],
        "decision_intelligence": master["decision_intelligence"],
        "explainability": master["explainability"],
        "incident_timeline": master["incident_timeline"],
        "validation": master["cross_notebook_validation"],
        "recommended_actions": _stakeholder_actions(master["decision_intelligence"], "police"),
    }


def build_bank_dashboard(master: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 13 entry point. Banks see financial-entity risk only.'''
    network = master["fraud_network_intelligence"]
    return {
        "case_id": master["case"]["case_id"],
        "money_mule_accounts": network.get("money_mule_accounts", []),
        "network_adjusted_risk": network.get("risk_propagation", {}).get("network_adjusted_risk"),
        "recommended_actions": _stakeholder_actions(master["decision_intelligence"], "bank"),
    }


def build_telecom_dashboard(master: Dict[str, Any]) -> Dict[str, Any]:
    '''Module 14 entry point. Telecom providers see phone/campaign risk only.'''
    entities = master["evidence"].get("metadata") or master["evidence"].get("extracted_entities") or {}
    network = master["fraud_network_intelligence"]
    return {
        "case_id": master["case"]["case_id"],
        "phone_numbers": entities.get("phone_numbers", []),
        "linked_campaigns": [c["campaign_id"] for c in network.get("fraud_campaigns", [])],
        "recommended_actions": _stakeholder_actions(master["decision_intelligence"], "telecom"),
    }


def build_administrator_dashboard(master: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Fifth audience view. Administrators care about platform health and
    pipeline performance, not case-specific investigative detail.

    IMPORTANT: this function requires master["audit_trail"],
    master["execution_statistics"], and master["engine_health"] to
    already be populated. The caller (process_case) MUST set those three
    keys on `master` BEFORE calling this function - that ordering is the
    fix for the Revision 3 KeyError bug.
    '''
    return {
        "case_id": master["case"]["case_id"],
        "engine_availability": master["engine_availability"],
        "engine_health": master["engine_health"],
        "audit_trail": master["audit_trail"],
        "execution_statistics": master["execution_statistics"],
        "total_cases_in_registry": CASE_REGISTRY.total_cases(),
        "cross_notebook_validation": master["cross_notebook_validation"],
    }

# ## 19. Executive Summary


# ============================================================================
# 19. Executive Summary
# ============================================================================


def build_executive_summary(master: Dict[str, Any]) -> Dict[str, Any]:
    '''
    One-screen summary an officer should be able to read in under 30
    seconds: what happened, how bad it is, and what is already known
    about it from the network and geography.
    '''
    network = master["fraud_network_intelligence"]
    geo = master["geospatial_intelligence"]
    fusion = master["threat_fusion"]

    top_community = network.get("communities", [{}])[0] if network.get("communities") else None
    top_hotspot = geo.get("hotspots", [{}])[0] if geo.get("hotspots") else None

    return {
        "case_id": master["case"]["case_id"],
        "fraud_type": master["fraud_intelligence"].get("fraud_type"),
        "threat_level": fusion["severity"],
        "overall_threat_score": fusion["overall_threat_score"],
        "overall_confidence": master["overall_confidence"],
        "amount_involved": master["case"]["amount_involved"],
        "connected_cases_count": len(network.get("connected_cases", [])),
        "campaign_id": network.get("fraud_campaigns", [{}])[0].get("campaign_id") if network.get("fraud_campaigns") else None,
        "money_mule_flagged": bool(network.get("money_mule_accounts")),
        "hotspot": top_hotspot["hotspot_id"] if top_hotspot else None,
        "hotspot_city": top_hotspot["primary_city"] if top_hotspot else None,
        "community_dominant_fraud": top_community.get("dominant_fraud") if top_community else None,
        "decision": _decision_category_label(master["decision_intelligence"]),
        "validation_conflicts": master["cross_notebook_validation"]["conflicts_found"],
    }

# ## 20. Platform Dashboard (compact, presentation-style summary)


# ============================================================================
# 20. Platform Dashboard (compact, presentation-style summary)
# ============================================================================


def build_platform_dashboard_text(master: Dict[str, Any]) -> str:
    '''Renders a compact, box-drawn summary block suitable for a terminal demo or a report cover page.'''
    exec_summary = master["executive_summary"]
    bar = "=" * 56
    lines = [
        bar,
        "DIGITAL PUBLIC SAFETY PLATFORM",
        bar,
        f"Case ID           : {exec_summary['case_id']}",
        f"Threat Level      : {exec_summary['threat_level'].upper()}",
        f"Fraud Type        : {exec_summary['fraud_type']}",
        f"Overall Threat    : {exec_summary['overall_threat_score']}/100",
        f"Confidence        : {exec_summary['overall_confidence']}%",
        f"Money Mule Flag   : {'YES' if exec_summary['money_mule_flagged'] else 'No'}",
        f"Campaign          : {exec_summary['campaign_id'] or 'None identified'}",
        f"Connected Cases   : {exec_summary['connected_cases_count']}",
        f"Hotspot           : {exec_summary['hotspot'] or 'None'} ({exec_summary['hotspot_city'] or 'n/a'})",
        f"Decision          : {exec_summary['decision']}",
        bar,
    ]
    return "\n".join(lines)

# ## 21. Final Intelligence Report (PDF, with plain-text fallback)


# ============================================================================
# 21. Final Intelligence Report (PDF, with plain-text fallback)
# ============================================================================


def _build_final_report_text_lines(master: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    lines.append(master["platform_dashboard_text"])
    lines.append("")

    lines.append("EXECUTIVE SUMMARY")
    for key, value in master["executive_summary"].items():
        lines.append(f"  {key}: {value}")
    lines.append("")

    lines.append("EXPLAINABILITY")
    for step in master["explainability"]:
        lines.append(f"  [{step['step']}] {step['detail']}")
    lines.append("")

    lines.append("INCIDENT TIMELINE")
    for event in master["incident_timeline"]:
        lines.append(f"  {event['timestamp']}  -  {event['event']}")
    lines.append("")

    if master["cross_notebook_validation"]["conflicts_found"]:
        lines.append("VALIDATION CONFLICTS")
        for conflict in master["cross_notebook_validation"]["conflicts_found"]:
            lines.append(f"  - {conflict}")
        lines.append("")

    lines.append("FRAUD INTELLIGENCE")
    lines.append(f"  Type: {master['fraud_intelligence'].get('fraud_type')}  |  Standalone risk: {master['fraud_intelligence'].get('risk_score')}")
    lines.append("")

    if master["counterfeit_intelligence"]:
        lines.append("COUNTERFEIT INTELLIGENCE")
        lines.append(f"  Verdict: {master['counterfeit_intelligence'].get('verdict')}")
        lines.append("")

    network = master["fraud_network_intelligence"]
    lines.append("FRAUD NETWORK INTELLIGENCE")
    lines.append(f"  Connected cases: {len(network.get('connected_cases', []))}")
    lines.append(f"  Communities: {len(network.get('communities', []))}  |  Money mule accounts: {len(network.get('money_mule_accounts', []))}")
    lines.append("")

    geo = master["geospatial_intelligence"]
    lines.append("GEOSPATIAL INTELLIGENCE")
    lines.append(f"  Hotspots: {len(geo.get('hotspots', []))}  |  Districts monitored: {len(geo.get('district_risk', []))}")
    lines.append("")

    lines.append("THREAT FUSION")
    fusion = master["threat_fusion"]
    lines.append(f"  Overall threat score: {fusion['overall_threat_score']} ({fusion['severity']})")
    for component, value in fusion["components"].items():
        lines.append(f"    {component}: {value}  (weight {fusion['weights'][component]})")
    lines.append("")

    decision = master["decision_intelligence"]
    lines.append("DECISION")
    lines.append(f"  Category: {_decision_category_label(decision)}")
    for reason in _decision_reasons(decision):
        lines.append(f"  Reason: {reason}")
    lines.append("")

    lines.append("ENGINE HEALTH")
    for stage, health in master["engine_health"].items():
        lines.append(f"  {stage:36s} | {health['status']}")
    lines.append("")

    lines.append("AUDIT TRAIL")
    for entry in master["audit_trail"]:
        lines.append(f"  {entry['stage']:36s} | {entry['engine_source']:36s} | {entry['duration_ms']} ms")
    lines.append("")

    lines.append("EXECUTION STATISTICS")
    for stage, seconds in master["execution_statistics"]["stage_seconds"].items():
        lines.append(f"  {stage:36s} {seconds:.3f} sec")
    lines.append(f"  {'TOTAL':36s} {master['execution_statistics']['total_seconds']:.3f} sec")

    return lines


def generate_final_intelligence_report(master: Dict[str, Any], output_path: str) -> str:
    '''
    Module 15 entry point. One PDF (or plain-text fallback) covering:
    platform dashboard, executive summary, explainability, incident
    timeline, validation conflicts, per-engine intelligence, threat
    fusion, decision, engine health, audit trail, and execution stats.

    NOTE: this function reads master["audit_trail"],
    master["execution_statistics"], master["engine_health"],
    master["executive_summary"], and master["platform_dashboard_text"],
    so the caller MUST populate all of those keys on `master` before
    calling this function.
    '''
    lines = _build_final_report_text_lines(master)

    if not _REPORTLAB_AVAILABLE:
        fallback_path = os.path.splitext(output_path)[0] + ".txt"
        with open(fallback_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        logger.info("reportlab not available; wrote plain-text final report to %s", fallback_path)
        return fallback_path

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=16)
    heading_style = ParagraphStyle("ReportHeading", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("ReportBody", parent=styles["BodyText"], spaceAfter=2)

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story: List[Any] = []

    story.append(Paragraph(f"Digital Public Safety Report - {master['package_id']}", title_style))
    story.append(Paragraph(f"Case: {master['case']['case_id']}", body_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Executive Summary", heading_style))
    for key, value in master["executive_summary"].items():
        story.append(Paragraph(f"<b>{key}:</b> {value}", body_style))

    story.append(Paragraph("Explainability", heading_style))
    for step in master["explainability"]:
        story.append(Paragraph(f"<b>{step['step']}:</b> {step['detail']}", body_style))

    story.append(Paragraph("Incident Timeline", heading_style))
    for event in master["incident_timeline"]:
        story.append(Paragraph(f"{event['timestamp']} - {event['event']}", body_style))

    if master["cross_notebook_validation"]["conflicts_found"]:
        story.append(Paragraph("Validation Conflicts", heading_style))
        for conflict in master["cross_notebook_validation"]["conflicts_found"]:
            story.append(Paragraph(conflict, body_style))

    story.append(Paragraph("Fraud Intelligence", heading_style))
    story.append(Paragraph(
        f"Type: {master['fraud_intelligence'].get('fraud_type')} | Standalone risk: {master['fraud_intelligence'].get('risk_score')}",
        body_style,
    ))

    if master["counterfeit_intelligence"]:
        story.append(Paragraph("Counterfeit Intelligence", heading_style))
        story.append(Paragraph(f"Verdict: {master['counterfeit_intelligence'].get('verdict')}", body_style))

    network = master["fraud_network_intelligence"]
    story.append(Paragraph("Fraud Network Intelligence", heading_style))
    story.append(Paragraph(
        f"Connected cases: {len(network.get('connected_cases', []))} | "
        f"Communities: {len(network.get('communities', []))} | "
        f"Money mule accounts: {len(network.get('money_mule_accounts', []))}",
        body_style,
    ))

    geo = master["geospatial_intelligence"]
    story.append(Paragraph("Geospatial Intelligence", heading_style))
    story.append(Paragraph(
        f"Hotspots: {len(geo.get('hotspots', []))} | Districts monitored: {len(geo.get('district_risk', []))}",
        body_style,
    ))

    fusion = master["threat_fusion"]
    story.append(Paragraph("Threat Fusion", heading_style))
    story.append(Paragraph(f"Overall threat score: {fusion['overall_threat_score']} ({fusion['severity']})", body_style))
    fusion_rows = [["Component", "Value", "Weight"]]
    for component, value in fusion["components"].items():
        fusion_rows.append([component, str(value), str(fusion["weights"][component])])
    fusion_table = Table(fusion_rows, colWidths=[6 * cm, 4 * cm, 3 * cm])
    fusion_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(fusion_table)

    decision = master["decision_intelligence"]
    story.append(Paragraph("Decision", heading_style))
    story.append(Paragraph(f"Category: {_decision_category_label(decision)}", body_style))
    for reason in _decision_reasons(decision):
        story.append(Paragraph(f"Reason: {reason}", body_style))

    story.append(PageBreak())
    story.append(Paragraph("Engine Health", heading_style))
    health_rows = [["Stage", "Status"]]
    for stage, health in master["engine_health"].items():
        health_rows.append([stage, health["status"]])
    health_table = Table(health_rows, colWidths=[6 * cm, 9 * cm])
    health_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ]))
    story.append(health_table)

    story.append(Paragraph("Audit Trail", heading_style))
    audit_rows = [["Stage", "Engine", "Duration (ms)"]]
    for entry in master["audit_trail"]:
        audit_rows.append([entry["stage"], entry["engine_source"], str(entry["duration_ms"])])
    audit_table = Table(audit_rows, colWidths=[6 * cm, 6 * cm, 3 * cm])
    audit_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ]))
    story.append(audit_table)

    story.append(Paragraph("Execution Statistics", heading_style))
    story.append(Paragraph(f"Total processing time: {master['execution_statistics']['total_seconds']:.3f} sec", body_style))

    doc.build(story)
    logger.info("Final intelligence report saved to %s", output_path)
    return output_path

# ## 22. Timing / audit wrapper


# ============================================================================
# 22. Timing / audit wrapper
# ============================================================================


def _run_stage(
    stage_name: str,
    engine_source: str,
    fn: Callable[[], Any],
    audit_trail: List[Dict[str, Any]],
    stage_seconds: Dict[str, float],
    required: bool = True,
    progress_callback: Optional[Callable[[str, float, str], None]] = None,
) -> Any:
    '''Shared timing/audit wrapper for every pipeline stage.'''
    start = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        audit_trail.append({"stage": stage_name, "status": "Failed", "engine_source": engine_source, "duration_ms": duration_ms})
        stage_seconds[stage_name] = round((time.perf_counter() - start), 4)
        if progress_callback:
            progress_callback(stage_name, duration_ms, "Failed")
        if required:
            raise OrchestrationError(f"Stage '{stage_name}' failed: {exc}") from exc
        logger.warning("Optional stage '%s' failed and was skipped: %s", stage_name, exc)
        return None

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    actual_source = result.get("engine_source", engine_source) if isinstance(result, dict) else engine_source
    status = "Completed" if result is not None else "Skipped"
    audit_trail.append({
        "stage": stage_name,
        "status": status,
        "engine_source": actual_source if result is not None else EngineSource.SKIPPED.value,
        "duration_ms": duration_ms,
    })
    stage_seconds[stage_name] = round((time.perf_counter() - start), 4)
    if progress_callback:
        progress_callback(stage_name, duration_ms, status)
    return result

# ## 23. Module 9 - Merge Everything / Orchestration Entry Point


# ============================================================================
# 23. Module 9 - Merge Everything / Orchestration Entry Point
# ============================================================================


def process_case(
    raw_case: CaseIntake,
    report_dir: str = "/tmp/notebook8_reports",
    progress_callback: Optional[Callable[[str, float, str], None]] = None,
) -> Dict[str, Any]:
    '''
    Notebook 8 orchestration.
    '''
    pipeline_start = time.perf_counter()
    audit_trail: List[Dict[str, Any]] = []
    stage_seconds: Dict[str, float] = {}

    # --- Step 1: analysis pipeline ---
    case = _run_stage("Case Intake", EngineSource.REAL.value, lambda: intake_case(raw_case), audit_trail, stage_seconds, progress_callback=progress_callback)
    routing_plan = _run_stage("Evidence Routing", EngineSource.REAL.value, lambda: route_evidence(case), audit_trail, stage_seconds, progress_callback=progress_callback)

    evidence_package = _run_stage(
        "Notebook 4 - Evidence Intelligence", EngineSource.REAL.value,
        lambda: run_evidence_engine(case), audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    fraud_package = _run_stage(
        "Notebook 2 - Fraud Intelligence", EngineSource.REAL.value,
        lambda: run_fraud_intelligence(case, evidence_package), audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    counterfeit_package = None
    if routing_plan["run_counterfeit_check"]:
        counterfeit_package = _run_stage(
            "Notebook 5 - Counterfeit Intelligence", EngineSource.REAL.value,
            lambda: run_counterfeit_check(case), audit_trail, stage_seconds, required=False, progress_callback=progress_callback,
        )

    network_package = _run_stage(
        "Notebook 6 - Fraud Network Intelligence", EngineSource.REAL.value,
        lambda: run_network_intelligence(case, evidence_package, fraud_package), audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    geo_package: Dict[str, Any] = {}
    if routing_plan["run_geospatial_intelligence"]:
        geo_package = _run_stage(
            "Notebook 7 - Geospatial Intelligence", EngineSource.REAL.value,
            lambda: run_geospatial_intelligence(case, fraud_package, network_package), audit_trail, stage_seconds, progress_callback=progress_callback,
        ) or {}

    threat_fusion = _run_stage(
        "Threat Fusion Engine", EngineSource.REAL.value,
        lambda: fuse_threat_score(case.case_id, fraud_package, network_package, geo_package, counterfeit_package),
        audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    confidence_fusion = _run_stage(
        "Confidence Fusion Engine", EngineSource.REAL.value,
        lambda: fuse_confidence(fraud_package, network_package, geo_package, counterfeit_package),
        audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    validation = _run_stage(
        "Cross-Notebook Validation", EngineSource.REAL.value,
        lambda: validate_cross_notebook_consistency(fraud_package, network_package, geo_package),
        audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    decision_package = _run_stage(
        "Notebook 3 - Decision Intelligence", EngineSource.REAL.value,
        lambda: run_decision_engine(fraud_package, network_package, counterfeit_package, threat_fusion, validation),
        audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    explainability = _run_stage(
        "Explainability", EngineSource.REAL.value,
        lambda: build_explainability(fraud_package, network_package, geo_package, threat_fusion, validation, decision_package),
        audit_trail, stage_seconds, progress_callback=progress_callback,
    )

    # --- Step 2: base master dict ---
    case_dict = {
        "case_id": case.case_id, "citizen_name": case.citizen_name, "victim_id": case.victim_id,
        "timestamp": case.timestamp, "city": case.city, "state": case.state,
        "priority": case.priority, "source": case.source, "amount_involved": case.amount_involved,
    }

    master: Dict[str, Any] = {
        "package_id": f"DPSP-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}",
        "case": case_dict,
        "evidence_routing_plan": routing_plan,
        "evidence": evidence_package,
        "fraud_intelligence": fraud_package,
        "counterfeit_intelligence": counterfeit_package,
        "fraud_network_intelligence": network_package,
        "geospatial_intelligence": geo_package,
        "threat_fusion": threat_fusion,
        "confidence_fusion": confidence_fusion,
        "cross_notebook_validation": validation,
        "decision_intelligence": decision_package,
        "explainability": explainability,
        "overall_threat_level": threat_fusion["overall_threat_score"],
        "overall_confidence": confidence_fusion["overall_confidence"],
        "engine_availability": {
            "notebook2_fraud_intelligence": _NOTEBOOK2_AVAILABLE,
            "notebook3_decision_intelligence": _NOTEBOOK3_AVAILABLE,
            "notebook4_evidence_intelligence": _NOTEBOOK4_AVAILABLE,
            "notebook5_counterfeit_intelligence": _NOTEBOOK5_AVAILABLE,
            "notebook6_network_intelligence": _NOTEBOOK6_AVAILABLE,
            "notebook7_geospatial_intelligence": _NOTEBOOK7_AVAILABLE,
        },
    }

    # --- Step 3: incident timeline ---
    master["incident_timeline"] = build_incident_timeline(
        case, evidence_package, fraud_package, network_package, geo_package, decision_package
    )

    # --- Step 4: audit_trail / execution_statistics (interim total) ---
    # THIS MUST HAPPEN BEFORE ANY DASHBOARD IS BUILT. This ordering is the
    # actual fix for the Revision 3 KeyError: 'audit_trail' bug.
    interim_total_seconds = round(time.perf_counter() - pipeline_start, 4)
    master["audit_trail"] = audit_trail
    master["execution_statistics"] = {
        "stage_seconds": stage_seconds,
        "total_seconds": interim_total_seconds,
    }

    # --- Step 5: engine_health (needs audit_trail, which now exists) ---
    master["engine_health"] = build_engine_health(audit_trail)

    # --- Step 6: executive summary and platform dashboard text ---
    master["executive_summary"] = build_executive_summary(master)
    master["platform_dashboard_text"] = build_platform_dashboard_text(master)

    # --- Step 7: all five audience dashboards, now safe to build ---
    master["citizen_response"] = build_citizen_dashboard(master)
    master["police_response"] = build_police_dashboard(master)
    master["bank_response"] = build_bank_dashboard(master)
    master["telecom_response"] = build_telecom_dashboard(master)
    master["administrator_response"] = build_administrator_dashboard(master)

    # --- Step 8: final report ---
    os.makedirs(report_dir, exist_ok=True)
    report_path = _run_stage(
        "Final Intelligence Report", EngineSource.REAL.value,
        lambda: generate_final_intelligence_report(master, os.path.join(report_dir, f"digital_public_safety_report_{uuid.uuid4().hex[:8]}.pdf")),
        audit_trail, stage_seconds,
    )
    master["final_report"] = report_path

    # --- Step 9: refresh audit-trail-derived fields after the report stage ---
    master["engine_health"] = build_engine_health(audit_trail)
    total_seconds = round(time.perf_counter() - pipeline_start, 4)
    master["execution_statistics"]["total_seconds"] = total_seconds
    # Keep the administrator dashboard's copies in sync with the refreshed values.
    master["administrator_response"]["engine_health"] = master["engine_health"]
    master["administrator_response"]["execution_statistics"] = master["execution_statistics"]

    case_digest = hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()
    master["audit"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_id_hash": case_digest,
        "notebook_version": CONFIG.NOTEBOOK_VERSION,
    }

    CASE_REGISTRY.register_master_package(case.case_id, master)

    logger.info(
        "Case processing complete. case_id=%s decision=%s threat_level=%s confidence=%s total_seconds=%.3f",
        case.case_id, _decision_category_label(decision_package),
        master["overall_threat_level"], master["overall_confidence"], total_seconds,
    )
    return master

# ## 24. Synthetic Case Generation and Deterministic Test Suite


# ============================================================================
# 24. Synthetic Case Generation and Deterministic Test Suite
# ============================================================================


def _build_synthetic_cases() -> List[CaseIntake]:
    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    cases: List[CaseIntake] = []

    # --- Three linked "Digital Arrest" cases, sharing a phone number and
    # UPI id, reported from Kolhapur then Pune. ---
    shared_phone = "9876543210"
    shared_upi = "rahul@okaxis"
    cities = ["Kolhapur", "Kolhapur", "Pune"]
    for i in range(1, 4):
        cases.append(CaseIntake(
            case_id=f"DPSP-CASE-{i:03d}",
            citizen_name=f"Citizen {i}",
            city=cities[i - 1],
            state="Maharashtra",
            timestamp=base_time.replace(day=min(28, base_time.day + i)).isoformat(),
            amount_involved=45000.0 + i * 5000,
            evidence=[
                EvidenceItem(
                    evidence_type="call_recording",
                    content=(
                        f"Caller claimed to be from CBI and RBI, said there is an arrest warrant against me, "
                        f"demanded a video call and payment via UPI to {shared_upi} to avoid digital arrest. "
                        f"Caller phone number was {shared_phone}."
                    ),
                ),
            ],
        ))

    # --- One case with a currency image (no real file on disk in this
    # test, so the counterfeit stub path is exercised). ---
    cases.append(CaseIntake(
        case_id="DPSP-CASE-CURRENCY-001",
        citizen_name="Citizen 4",
        city="Mumbai",
        state="Maharashtra",
        timestamp=base_time.replace(day=15).isoformat(),
        amount_involved=500.0,
        evidence=[
            EvidenceItem(evidence_type="text", content="I received this 500 rupee note as change and it feels off."),
            EvidenceItem(
                evidence_type="currency_image",
                content="note_scan_001.jpg",
                metadata={"citizen_reported_suspicious": True},
            ),
        ],
    ))

    # --- One low-signal case with no fraud keywords, no location, and a
    # tiny amount, to exercise the No Action decision path. ---
    cases.append(CaseIntake(
        case_id="DPSP-CASE-LOWSIGNAL-001",
        citizen_name="Citizen 5",
        timestamp=base_time.replace(day=20).isoformat(),
        amount_involved=200.0,
        evidence=[EvidenceItem(evidence_type="text", content="Just wanted to ask a general question about safe UPI usage.")],
    ))

    return cases


def run_notebook8_test_suite() -> Dict[str, Any]:
    print("=== Notebook 8 Test Suite: end-to-end Digital Public Safety Platform (Revision 4) ===\n")

    cases = _build_synthetic_cases()
    checks: List[bool] = []
    results: List[Dict[str, Any]] = []

    def _check(label: str, actual: Any, expected: Any) -> None:
        ok = actual == expected
        checks.append(ok)
        print(f"    [{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")

    def _check_true(label: str, condition: bool) -> None:
        checks.append(condition)
        print(f"    [{'PASS' if condition else 'FAIL'}] {label}")

    print("--- Processing cases sequentially through the orchestrator ---")
    for case in cases:
        print(f"\nProcessing {case.case_id} ...")
        master = process_case(case)
        results.append(master)
        print(master["platform_dashboard_text"])

    ring_result = results[2]
    currency_result = results[3]
    low_signal_result = results[4]

    # --- Case intake / routing ---
    _check("first case id preserved", results[0]["case"]["case_id"], "DPSP-CASE-001")
    _check_true("currency case routed counterfeit check on", currency_result["evidence_routing_plan"]["run_counterfeit_check"])
    _check_true("linked-ring case routed counterfeit check off", ring_result["evidence_routing_plan"]["run_counterfeit_check"] is False)

    # --- Evidence engine ---
    entities = ring_result["evidence"].get("metadata") or ring_result["evidence"].get("extracted_entities") or {}
    _check_true("phone number extracted from ring case evidence", "9876543210" in entities.get("phone_numbers", []))

    # --- Fraud intelligence ---
    _check_true("low-signal case classified without a hard crash",
                low_signal_result["fraud_intelligence"].get("fraud_type") is not None)

    # --- Threat fusion ---
    fusion = ring_result["threat_fusion"]
    _check_true("threat fusion score is within 0-100", 0.0 <= fusion["overall_threat_score"] <= 100.0)
    _check_true("threat fusion reports all four components",
                set(fusion["components"].keys()) == {"fraud_standalone_risk", "network_adjusted_risk", "geospatial_signal", "counterfeit_signal"})

    # --- Confidence fusion ---
    conf = ring_result["confidence_fusion"]
    _check_true("confidence fusion score is within 0-100", 0.0 <= conf["overall_confidence"] <= 100.0)

    # --- Cross-notebook validation ---
    _check_true("validation result carries a boolean consistency flag", isinstance(ring_result["cross_notebook_validation"]["is_consistent"], bool))

    # --- Counterfeit intelligence ---
    _check_true("counterfeit check ran for currency case", currency_result["counterfeit_intelligence"] is not None)
    _check_true("counterfeit check did not run for ring case", ring_result["counterfeit_intelligence"] is None)

    # --- Decision intelligence ---
    _check_true("decision category was produced for every case",
                all(_decision_category_label(r["decision_intelligence"]) != "Unknown" for r in results))

    # --- Explainability / timeline ---
    _check_true("explainability chain ends with the final decision",
                ring_result["explainability"][-1]["detail"] == _decision_category_label(ring_result["decision_intelligence"]))
    _check_true("incident timeline is non-empty", len(ring_result["incident_timeline"]) > 0)

    # --- Executive summary / platform dashboard ---
    _check_true("executive summary carries a threat_level", "threat_level" in ring_result["executive_summary"])
    _check_true("platform dashboard text is a non-empty string", isinstance(ring_result["platform_dashboard_text"], str) and len(ring_result["platform_dashboard_text"]) > 0)

    # --- Dashboards (the key regression check for this revision) ---
    citizen_dash = ring_result["citizen_response"]
    police_dash = ring_result["police_response"]
    bank_dash = ring_result["bank_response"]
    telecom_dash = ring_result["telecom_response"]
    admin_dash = ring_result["administrator_response"]

    _check_true("citizen dashboard excludes raw network graph internals", "fraud_network_intelligence" not in citizen_dash)
    _check_true("citizen dashboard carries the national helpline", citizen_dash["national_cyber_crime_helpline"] == "1930")
    _check_true("police dashboard includes full network intelligence", "fraud_network_intelligence" in police_dash)
    _check_true("bank dashboard is scoped to financial entities only",
                set(bank_dash.keys()) == {"case_id", "money_mule_accounts", "network_adjusted_risk", "recommended_actions"})
    _check_true("telecom dashboard is scoped to phone/campaign info only",
                set(telecom_dash.keys()) == {"case_id", "phone_numbers", "linked_campaigns", "recommended_actions"})
    _check_true("administrator dashboard was built without a KeyError (Revision 4 regression test)",
                admin_dash is not None and "engine_health" in admin_dash and "audit_trail" in admin_dash
                and "execution_statistics" in admin_dash and "total_cases_in_registry" in admin_dash
                and "cross_notebook_validation" in admin_dash)
    _check_true("administrator dashboard's execution_statistics total accounts for report generation time",
                admin_dash["execution_statistics"]["total_seconds"] >= admin_dash["execution_statistics"]["stage_seconds"].get("Final Intelligence Report", 0.0))

    # --- Case registry ---
    _check("case registry has processed all synthetic cases", CASE_REGISTRY.total_cases(), len(cases))

    # --- Master package structure ---
    expected_keys = {
        "package_id", "case", "evidence_routing_plan", "evidence", "fraud_intelligence",
        "counterfeit_intelligence", "fraud_network_intelligence", "geospatial_intelligence",
        "threat_fusion", "confidence_fusion", "cross_notebook_validation", "decision_intelligence",
        "explainability", "incident_timeline", "engine_health", "executive_summary",
        "platform_dashboard_text", "overall_threat_level", "overall_confidence", "engine_availability",
        "citizen_response", "police_response", "bank_response", "telecom_response", "administrator_response",
        "final_report", "audit_trail", "execution_statistics", "audit",
    }
    _check_true("master package contains all expected top-level keys", expected_keys.issubset(set(ring_result.keys())))

    # --- Audit trail / performance statistics ---
    _check_true("audit trail has an entry for every pipeline stage", len(ring_result["audit_trail"]) >= 10)
    _check_true("execution statistics report a positive total time", ring_result["execution_statistics"]["total_seconds"] > 0)

    # --- Final report ---
    _check_true("final intelligence report file was generated", ring_result["final_report"] is not None)
    _check_true("final intelligence report file exists on disk", os.path.exists(ring_result["final_report"]))

    print(f"\nSUMMARY: {sum(checks)}/{len(checks)} checks passed\n")

    print("Overall results by case:")
    for m in results:
        print(
            f"  {m['case']['case_id']:26s} threat={m['overall_threat_level']:6.1f} "
            f"decision={_decision_category_label(m['decision_intelligence']):20s} "
            f"confidence={m['overall_confidence']}%"
        )

    print(f"\nEngine availability: {json.dumps(ring_result['engine_availability'], indent=2)}")
    print(f"\nEngine health for {ring_result['case']['case_id']}:")
    for stage, health in ring_result["engine_health"].items():
        print(f"  {stage:36s} | {health['status']}")

    print(f"\nFinal report file: {ring_result['final_report']}")

    return {"results": results, "checks_passed": sum(checks), "checks_total": len(checks)}


if __name__ == "__main__":
    run_notebook8_test_suite()

