# Generated from: decision_intelligence_engine__.ipynb
# Converted at: 2026-07-15T01:45:22.870Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # Decision Intelligence Engine
# ### ET AI Hackathon 2026 -- Digital Public Safety Platform (PS6)
# ### Notebook 3 -- Decision Intelligence Engine (Case-Management Edition)
# 
# decision_intelligence_engine.py
# ET AI Hackathon 2026 — Digital Public Safety Platform (PS6)
# Notebook 3 — Decision Intelligence Engine (Case-Management Edition)
# 
# Notebook 2 (Fraud_Intelligence_Engine) decides WHAT is happening.
# Notebook 3 decides WHAT SHOULD HAPPEN NEXT — and now also tracks the
# case as it moves through its lifecycle, the same way a real incident
# management / command-center product would.
# 
# Design principle (unchanged): Notebook 3 never re-analyses raw text,
# never calls an LLM for its core decisions, and never touches the vector
# store. Everything is deterministic — policy rules, mappings, and
# templates. New in this version: a Case Management Layer (lifecycle,
# fraud stage, financial exposure, evidence strength, recovery odds,
# completion tracking, notification queue, pattern IDs) that turns the
# static decision package into a stateful incident record.
# 
# Input: exactly one JSON object — the output of analyze_case() from
# Notebook 2 — plus a few OPTIONAL state-update objects (which actions the
# citizen has completed so far, which notifications have gone out, and,
# if Notebook 2's RAG layer supplied them, similar historical cases).
# None of these optional inputs are generated inside this notebook.


# ## Imports and Logging Setup


import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("decision_intelligence_engine")

# ## 1. Configuration


class Config:
    '''Central configuration for Notebook 3.'''

    # --- Case decision thresholds ---
    EMERGENCY_RISK_THRESHOLD: int = 90
    ESCALATION_RISK_THRESHOLD: int = 85
    LOW_RISK_AWARENESS_ONLY: int = 40
    LOW_CONFIDENCE_HUMAN_REVIEW: int = 50

    # --- Multilingual ---
    SUPPORTED_LANGUAGES: List[str] = ["en", "hi", "mr", "ta", "kn", "te", "gu", "pa"]
    DEFAULT_LANGUAGES: List[str] = ["en", "hi", "mr"]
    ENABLE_LLM_LANGUAGE_REWRITE: bool = False

    # --- Case management layer ---
    DECISION_POLICY_VERSION: str = "v1.2"
    PATTERN_ID_PREFIX: Dict[str, str] = {
        "Digital Arrest Scam": "DA",
        "UPI / Payment Fraud": "UPI",
        "Phishing / Credential Theft": "PHI",
        "Extortion / Threat-based Fraud": "EXT",
        "Investment Scam": "INV",
        "Counterfeit Currency": "CFC",
        "Identity Theft": "IDT",
    }
    DEFAULT_PATTERN_PREFIX: str = "GEN"

    # Recovery-probability heuristics (money not yet transferred vs. transferred)
    RECOVERY_SCORE_NO_TRANSFER: int = 95
    RECOVERY_SCORE_TRANSFERRED: int = 45
    RECOVERY_SCORE_UNKNOWN: int = 65

    # Risk points removed by completing a given class of citizen action.
    # Purely illustrative/deterministic — not learned, not LLM-derived.
    RISK_REDUCTION_WEIGHTS: Dict[str, int] = {
        "disconnect": 30,
        "no_money": 25,
        "no_otp_or_credentials": 15,
        "report": 15,
        "block": 10,
        "evidence": 5,
    }


CONFIG = Config()
logger.info(
    "Notebook 3 configuration loaded. emergency_threshold=%d escalation_threshold=%d policy_version=%s",
    CONFIG.EMERGENCY_RISK_THRESHOLD, CONFIG.ESCALATION_RISK_THRESHOLD, CONFIG.DECISION_POLICY_VERSION,
)

# ## 2. Core Enums


class Priority(str, Enum):
    IMMEDIATE = "Immediate"
    URGENT = "Urgent"
    STANDARD = "Standard"
    ROUTINE = "Routine"


class Timeframe(str, Enum):
    IMMEDIATE = "Immediately"
    WITHIN_5_MIN = "Within 5 minutes"
    WITHIN_30_MIN = "Within 30 minutes"
    WITHIN_24_HOURS = "Within 24 hours"


class Stakeholder(str, Enum):
    CITIZEN = "Citizen"
    BANK = "Bank"
    TELECOM = "Telecom"
    POLICE = "Police"
    CYBER_CELL = "Cyber Cell"
    NPCI = "NPCI"
    SEBI = "SEBI"
    RBI = "RBI"
    UIDAI = "UIDAI"
    ADMINISTRATOR = "Administrator"


class CaseDecision(str, Enum):
    EMERGENCY = "Emergency"
    URGENT_ACTION = "Urgent Action"
    AWARENESS_ONLY = "Awareness Only"
    NEEDS_HUMAN_REVIEW = "Needs Human Review"
    NO_ACTION = "No Action - Benign"


class Persona(str, Enum):
    GENERAL_CITIZEN = "General Citizen"
    SENIOR_CITIZEN = "Senior Citizen"
    STUDENT = "Student"
    BUSINESS_OWNER = "Business Owner"
    BANK_EMPLOYEE = "Bank Employee"
    POLICE_OFFICER = "Police Officer"


class CaseStatus(str, Enum):
    '''New: Case Lifecycle (feature 1).'''
    DETECTED = "Detected"
    UNDER_INVESTIGATION = "Under Investigation"
    EVIDENCE_COLLECTED = "Evidence Collected"
    REPORTED = "Reported"
    BANK_ACTION = "Bank Action"
    POLICE_ACTION = "Police Action"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


# Fixed, linear lifecycle order used for validation / "next status" helpers.
_CASE_STATUS_ORDER: List[CaseStatus] = [
    CaseStatus.DETECTED,
    CaseStatus.UNDER_INVESTIGATION,
    CaseStatus.EVIDENCE_COLLECTED,
    CaseStatus.REPORTED,
    CaseStatus.BANK_ACTION,
    CaseStatus.POLICE_ACTION,
    CaseStatus.RESOLVED,
    CaseStatus.CLOSED,
]


class FraudStage(str, Enum):
    '''New: Fraud Stage (feature 3) — how far the scam has actually progressed.'''
    CONTACT = "Contact"
    TRUST_BUILDING = "Trust Building"
    THREAT = "Threat"
    MONEY_DEMAND = "Money Demand"
    MONEY_SENT = "Money Sent"
    UNKNOWN = "Unknown"


class NotificationStatus(str, Enum):
    '''New: Notification Queue (feature 8).'''
    PENDING = "Pending"
    SENT = "Sent"
    DELIVERED = "Delivered"
    ACKNOWLEDGED = "Acknowledged"


class EvidenceStrength(str, Enum):
    '''New: Evidence Strength (feature 7).'''
    WEAK = "Weak"
    MODERATE = "Moderate"
    STRONG = "Strong"
    COURT_READY = "Court Ready"


class DecisionIntelligenceError(Exception):
    '''Raised when Notebook 3 cannot produce a valid decision package.'''

# ## 3. Module 1 — Intelligence Parser


@dataclass
class CaseIntelligence:
    case_id: str
    fraud_type: str
    risk_score: int
    confidence: int
    severity: str
    indicators: List[str]
    unvalidated_indicators: List[str]
    entities: Dict[str, List[str]]
    evidence_citations: Dict[str, List[int]]
    reasoning_summary: str
    timestamp: str
    raw: Dict[str, Any] = field(default_factory=dict)


_REQUIRED_FIELDS = ("fraud_type", "risk_score", "confidence", "severity")


def parse_intelligence(notebook2_output: Dict[str, Any]) -> CaseIntelligence:
    '''Validates required fields and builds a typed CaseIntelligence object.'''
    missing = [f for f in _REQUIRED_FIELDS if f not in notebook2_output]
    if missing:
        raise DecisionIntelligenceError(
            f"Notebook 2 output is missing required field(s): {missing}. "
            f"Notebook 3 cannot make decisions without complete intelligence."
        )

    case_id = notebook2_output.get("case_id") or str(uuid.uuid4())
    parsed = CaseIntelligence(
        case_id=case_id,
        fraud_type=notebook2_output["fraud_type"],
        risk_score=int(notebook2_output["risk_score"]),
        confidence=int(notebook2_output["confidence"]),
        severity=notebook2_output["severity"],
        indicators=list(notebook2_output.get("indicators", [])),
        unvalidated_indicators=list(notebook2_output.get("unvalidated_indicators", [])),
        entities=dict(notebook2_output.get("entities", {})),
        evidence_citations=dict(notebook2_output.get("citations", {})),
        reasoning_summary=notebook2_output.get("summary", notebook2_output.get("reasoning_summary", "")),
        timestamp=notebook2_output.get("timestamp", datetime.now(timezone.utc).isoformat()),
        raw=notebook2_output,
    )
    logger.info(
        "Parsed intelligence for case %s. fraud_type=%s risk=%d confidence=%d",
        parsed.case_id, parsed.fraud_type, parsed.risk_score, parsed.confidence,
    )
    return parsed

# ## 4. Module 2 — Decision Policy Engine


_UNCLASSIFIED_LABELS = {"Unclassified Suspicious Activity", "Unclassified", ""}


def determine_case_decision(intel: CaseIntelligence) -> Dict[str, Any]:
    '''
    Policy order (first match wins):
      1. Unclassified + zero risk               -> No Action
      2. Confidence below review threshold        -> Needs Human Review
      3. Risk >= EMERGENCY_RISK_THRESHOLD         -> Emergency
      4. Risk >= ESCALATION_RISK_THRESHOLD        -> Urgent Action
      5. Risk <= LOW_RISK_AWARENESS_ONLY          -> Awareness Only
      6. Otherwise (medium band)                  -> Urgent Action
    '''
    reasons: List[str] = []

    if intel.fraud_type in _UNCLASSIFIED_LABELS and intel.risk_score == 0:
        reasons.append("Case is unclassified with zero risk score.")
        decision = CaseDecision.NO_ACTION
    elif intel.confidence < CONFIG.LOW_CONFIDENCE_HUMAN_REVIEW:
        reasons.append(
            f"Confidence ({intel.confidence}) is below the human-review threshold ({CONFIG.LOW_CONFIDENCE_HUMAN_REVIEW})."
        )
        decision = CaseDecision.NEEDS_HUMAN_REVIEW
    elif intel.risk_score >= CONFIG.EMERGENCY_RISK_THRESHOLD:
        reasons.append(f"Risk score ({intel.risk_score}) >= emergency threshold ({CONFIG.EMERGENCY_RISK_THRESHOLD}).")
        decision = CaseDecision.EMERGENCY
    elif intel.risk_score >= CONFIG.ESCALATION_RISK_THRESHOLD:
        reasons.append(f"Risk score ({intel.risk_score}) >= escalation threshold ({CONFIG.ESCALATION_RISK_THRESHOLD}).")
        decision = CaseDecision.URGENT_ACTION
    elif intel.risk_score <= CONFIG.LOW_RISK_AWARENESS_ONLY:
        reasons.append(f"Risk score ({intel.risk_score}) <= awareness-only threshold ({CONFIG.LOW_RISK_AWARENESS_ONLY}).")
        decision = CaseDecision.AWARENESS_ONLY
    else:
        reasons.append(f"Risk score ({intel.risk_score}) is in the medium band; defaulting to urgent action.")
        decision = CaseDecision.URGENT_ACTION

    logger.info("Case %s decision=%s", intel.case_id, decision.value)
    return {"decision": decision.value, "policy_reasons": reasons}

# ## 5. Module 3 — Stakeholder Identification


_FRAUD_TYPE_STAKEHOLDERS: Dict[str, List[Stakeholder]] = {
    "Digital Arrest Scam": [Stakeholder.CITIZEN, Stakeholder.POLICE, Stakeholder.TELECOM, Stakeholder.CYBER_CELL],
    "UPI / Payment Fraud": [Stakeholder.CITIZEN, Stakeholder.BANK, Stakeholder.NPCI],
    "Phishing / Credential Theft": [Stakeholder.CITIZEN, Stakeholder.BANK, Stakeholder.CYBER_CELL],
    "Extortion / Threat-based Fraud": [Stakeholder.CITIZEN, Stakeholder.POLICE, Stakeholder.CYBER_CELL],
    "Investment Scam": [Stakeholder.CITIZEN, Stakeholder.SEBI, Stakeholder.BANK],
    "Counterfeit Currency": [Stakeholder.CITIZEN, Stakeholder.BANK, Stakeholder.POLICE, Stakeholder.RBI],
    "Identity Theft": [Stakeholder.CITIZEN, Stakeholder.UIDAI, Stakeholder.POLICE],
}
_DEFAULT_STAKEHOLDERS: List[Stakeholder] = [Stakeholder.CITIZEN]


def identify_stakeholders(intel: CaseIntelligence, decision: str) -> List[str]:
    if decision == CaseDecision.NO_ACTION.value:
        return [Stakeholder.CITIZEN.value]

    stakeholders = list(_FRAUD_TYPE_STAKEHOLDERS.get(intel.fraud_type, _DEFAULT_STAKEHOLDERS))
    if Stakeholder.CITIZEN not in stakeholders:
        stakeholders = [Stakeholder.CITIZEN] + stakeholders

    if decision == CaseDecision.EMERGENCY.value and Stakeholder.ADMINISTRATOR not in stakeholders:
        stakeholders = stakeholders + [Stakeholder.ADMINISTRATOR]

    result = [s.value for s in stakeholders]
    logger.info("Case %s stakeholders=%s", intel.case_id, result)
    return result

# ## 6. Module 4 — Decision Matrix


@dataclass
class StakeholderAction:
    action: str
    reason: str
    priority: str
    timeframe: str
    action_id: str = ""   # New: stable id used by the completion tracker (feature 5)


_INDICATOR_REASON_TEXT: Dict[str, str] = {
    "Government Impersonation": "Government impersonation detected.",
    "Threat Language": "Threatening or coercive language detected.",
    "Urgency": "Artificial urgency detected.",
    "Isolation Tactics": "Isolation tactics detected (caller discouraged disconnecting or informing others).",
    "Money Demand": "A money transfer or payment was demanded.",
    "Urgent Payment Request": "An urgent payment request was detected.",
    "Criminal Allegation": "A false or unverified criminal allegation was made against the citizen.",
    "Suspicious Link": "A suspicious or unverified link was shared.",
    "OTP Request": "The message requested or referenced an OTP.",
    "Blackmail / Extortion Threat": "A blackmail or extortion threat was detected.",
}

_DECISION_MATRIX: Dict[str, Dict[Stakeholder, List[Tuple[str, List[str], Priority, Timeframe]]]] = {
    "Digital Arrest Scam": {
        Stakeholder.CITIZEN: [
            ("Disconnect the call immediately", ["Isolation Tactics", "Government Impersonation"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Do NOT transfer any money", ["Money Demand", "Urgent Payment Request"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Do not share OTP, PAN, or Aadhaar details over the call", ["Government Impersonation"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Report the incident on the 1930 helpline", ["Government Impersonation", "Criminal Allegation"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Save call screenshots and recordings as evidence", ["Government Impersonation"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Block the caller's number", ["Government Impersonation"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
        Stakeholder.POLICE: [
            ("Register a cyber crime complaint", ["Government Impersonation", "Criminal Allegation"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Collect call logs and caller number details", ["Government Impersonation"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Preserve all submitted evidence for investigation", ["Government Impersonation"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
        Stakeholder.TELECOM: [
            ("Check the caller number for spoofing", ["Government Impersonation"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Trace call routing origin", ["Government Impersonation"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
            ("Suspend the number pending investigation", ["Government Impersonation"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
        Stakeholder.CYBER_CELL: [
            ("Log the case in the national cybercrime database", ["Government Impersonation"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
    },
    "UPI / Payment Fraud": {
        Stakeholder.CITIZEN: [
            ("Do not transfer or reverse any funds on request", ["Money Demand", "Urgent Payment Request"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Do not share the OTP with anyone", ["OTP Request"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Report the UPI ID / transaction to your bank", ["Money Demand"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("File a complaint on the 1930 helpline or cybercrime.gov.in", ["Money Demand"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
        Stakeholder.BANK: [
            ("Flag and monitor the linked account for suspicious activity", ["Money Demand"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Freeze the receiving account if funds were transferred", ["Money Demand"], Priority.IMMEDIATE, Timeframe.WITHIN_5_MIN),
        ],
        Stakeholder.NPCI: [
            ("Flag the UPI handle for review", ["Money Demand", "Suspicious Link"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
    },
    "Phishing / Credential Theft": {
        Stakeholder.CITIZEN: [
            ("Do not click the shared link", ["Suspicious Link"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Do not enter OTP, passwords, or card details on the link", ["Suspicious Link", "OTP Request"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Change passwords for any account you may have entered", ["Suspicious Link"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
        Stakeholder.BANK: [
            ("Monitor the account for unauthorized login attempts", ["Suspicious Link", "OTP Request"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
        Stakeholder.CYBER_CELL: [
            ("Add the phishing URL to the blocklist", ["Suspicious Link"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
    },
    "Extortion / Threat-based Fraud": {
        Stakeholder.CITIZEN: [
            ("Do not pay the demanded amount", ["Blackmail / Extortion Threat", "Money Demand"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Do not engage further with the sender", ["Blackmail / Extortion Threat"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Preserve all messages, screenshots, and payment demands as evidence", ["Blackmail / Extortion Threat"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
            ("Report the incident on the 1930 helpline", ["Blackmail / Extortion Threat", "Threat Language"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
        Stakeholder.POLICE: [
            ("Register a complaint under relevant cyber extortion provisions", ["Blackmail / Extortion Threat"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
        Stakeholder.CYBER_CELL: [
            ("Preserve evidence and begin takedown request if content was shared", ["Blackmail / Extortion Threat"], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
    },
    "Investment Scam": {
        Stakeholder.CITIZEN: [
            ("Do not invest further funds", ["Money Demand"], Priority.IMMEDIATE, Timeframe.IMMEDIATE),
            ("Verify the platform's SEBI registration before any transaction", [], Priority.URGENT, Timeframe.WITHIN_30_MIN),
        ],
        Stakeholder.SEBI: [
            ("Flag the unregistered investment platform for review", [], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
        Stakeholder.BANK: [
            ("Monitor for further outbound transfers to the same beneficiary", ["Money Demand"], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
        ],
    },
}

_DEFAULT_CITIZEN_ACTIONS: List[Tuple[str, List[str], Priority, Timeframe]] = [
    ("Do not act on the request until you have verified it independently", [], Priority.STANDARD, Timeframe.WITHIN_24_HOURS),
    ("If money or credentials were already shared, contact your bank and file a complaint at cybercrime.gov.in", [], Priority.URGENT, Timeframe.WITHIN_30_MIN),
]


def _make_action_id(stakeholder: str, index: int) -> str:
    slug = stakeholder.lower().replace(" ", "-")
    return f"{slug}-{index:02d}"


def _default_citizen_only(note: str) -> Dict[str, List[StakeholderAction]]:
    actions = []
    for idx, (action, _driving, priority, timeframe) in enumerate(_DEFAULT_CITIZEN_ACTIONS):
        actions.append(StakeholderAction(
            action=action, reason=note, priority=priority.value, timeframe=timeframe.value,
            action_id=_make_action_id(Stakeholder.CITIZEN.value, idx),
        ))
    return {Stakeholder.CITIZEN.value: actions}


def build_decision_matrix(intel: CaseIntelligence, stakeholders: List[str]) -> Dict[str, List[StakeholderAction]]:
    matrix = _DECISION_MATRIX.get(intel.fraud_type)
    if matrix is None:
        logger.warning("No decision-matrix entry for fraud_type=%s; using default citizen guidance.", intel.fraud_type)
        return _default_citizen_only("No stakeholder-specific policy exists for this fraud type; default caution advised.")

    case_indicator_set = set(intel.indicators)
    result: Dict[str, List[StakeholderAction]] = {}

    for stakeholder_name in stakeholders:
        try:
            stakeholder_enum = Stakeholder(stakeholder_name)
        except ValueError:
            continue
        actions: List[StakeholderAction] = []
        for idx, (action_text, driving_indicators, priority, timeframe) in enumerate(matrix.get(stakeholder_enum, [])):
            if driving_indicators:
                matched = [i for i in driving_indicators if i in case_indicator_set]
                if not matched:
                    continue
                reason = " ".join(_INDICATOR_REASON_TEXT.get(i, i) for i in matched)
            else:
                reason = "Standard precaution for this fraud type, applicable regardless of specific indicators."
            actions.append(StakeholderAction(
                action=action_text, reason=reason, priority=priority.value, timeframe=timeframe.value,
                action_id=_make_action_id(stakeholder_name, idx),
            ))
        if actions:
            result[stakeholder_name] = actions

    if not result:
        return _default_citizen_only("No specific indicators matched the decision matrix; default caution advised.")
    return result

# ## 7. Module 5 — Action Prioritization


_PRIORITY_ORDER: Dict[str, int] = {
    Priority.IMMEDIATE.value: 0,
    Priority.URGENT.value: 1,
    Priority.STANDARD.value: 2,
    Priority.ROUTINE.value: 3,
}


def prioritize_actions(decision_matrix: Dict[str, List[StakeholderAction]]) -> Dict[str, List[StakeholderAction]]:
    return {
        stakeholder: sorted(actions, key=lambda a: _PRIORITY_ORDER.get(a.priority, 99))
        for stakeholder, actions in decision_matrix.items()
    }

# ## 8. Module 6 — Timeline Generator


def generate_timeline(prioritized_actions: Dict[str, List[StakeholderAction]]) -> Dict[str, List[Dict[str, Any]]]:
    timeframe_order = [t.value for t in Timeframe]
    timeline: Dict[str, List[Dict[str, Any]]] = {}

    for stakeholder, actions in prioritized_actions.items():
        by_timeframe: Dict[str, List[str]] = {}
        for action in actions:
            by_timeframe.setdefault(action.timeframe, []).append(action.action)
        timeline[stakeholder] = [
            {"timeframe": tf, "actions": by_timeframe[tf]}
            for tf in timeframe_order
            if tf in by_timeframe
        ]
    return timeline

# ## 9. Module 7 — Escalation Engine


@dataclass
class EscalationResult:
    escalate: bool
    escalation_level: str
    escalate_to: List[str]
    reason: str


def determine_escalation(intel: CaseIntelligence, decision: str) -> EscalationResult:
    if decision == CaseDecision.EMERGENCY.value:
        return EscalationResult(
            escalate=True, escalation_level="Emergency",
            escalate_to=[Stakeholder.CYBER_CELL.value, Stakeholder.POLICE.value],
            reason=f"Risk score {intel.risk_score} meets the Emergency threshold ({CONFIG.EMERGENCY_RISK_THRESHOLD}).",
        )
    if decision == CaseDecision.URGENT_ACTION.value and intel.risk_score >= CONFIG.ESCALATION_RISK_THRESHOLD:
        return EscalationResult(
            escalate=True, escalation_level="Standard",
            escalate_to=[Stakeholder.CYBER_CELL.value],
            reason=f"Risk score {intel.risk_score} meets the escalation threshold ({CONFIG.ESCALATION_RISK_THRESHOLD}).",
        )
    if decision == CaseDecision.NEEDS_HUMAN_REVIEW.value:
        return EscalationResult(
            escalate=True, escalation_level="Standard",
            escalate_to=[Stakeholder.ADMINISTRATOR.value],
            reason=f"Confidence ({intel.confidence}) is too low for automated handling; routed to a human reviewer.",
        )
    return EscalationResult(
        escalate=False, escalation_level="None", escalate_to=[],
        reason="Risk score and confidence do not meet any escalation threshold.",
    )

# ## 10. Module 8 — Recommendation Generator


def generate_recommendations(prioritized_actions: Dict[str, List[StakeholderAction]]) -> Dict[str, List[str]]:
    return {stakeholder: [a.action for a in actions] for stakeholder, actions in prioritized_actions.items()}

# ## 11. Module 9 — Explainability Engine (+ AI Explanation Card, feature 15)


def build_explainability_report(prioritized_actions: Dict[str, List[StakeholderAction]]) -> List[Dict[str, str]]:
    report: List[Dict[str, str]] = []
    for stakeholder, actions in prioritized_actions.items():
        for action in actions:
            report.append({"stakeholder": stakeholder, "action": action.action, "reason": action.reason})
    return report


def build_explanation_card(intel: CaseIntelligence, decision: str) -> Dict[str, Any]:
    '''
    New (feature 15): a single, judge-readable "why did the AI classify this?"
    card. Purely a re-presentation of Notebook 2's validated indicators and
    Notebook 3's own confidence banding — no new inference happens here.
    '''
    return {
        "question": "Why did the AI classify this case the way it did?",
        "matched_signals": [
            _INDICATOR_REASON_TEXT.get(i, i) for i in intel.indicators
        ] or ["No validated indicators were present."],
        "unvalidated_signals_excluded": intel.unvalidated_indicators,
        "matched_advisory_reference": (
            "Matched I4C advisory pattern for this fraud type."
            if intel.fraud_type in _DECISION_MATRIX else
            "No specific advisory pattern on file for this fraud type; generic caution applied."
        ),
        "confidence_pct": intel.confidence,
        "decision_reliability": _decision_reliability_label(intel.confidence),
        "final_decision": decision,
    }


def _decision_reliability_label(confidence: int) -> str:
    '''New (feature 12): decision reliability label, distinct from raw confidence %.'''
    if confidence >= 90:
        return "Very High"
    if confidence >= 75:
        return "High"
    if confidence >= 50:
        return "Medium"
    return "Low"

# ## 12. Module 10 — Severity Verification


_SEVERITY_PRIORITY_MAP: Dict[str, str] = {
    "Critical": Priority.IMMEDIATE.value,
    "High": Priority.URGENT.value,
    "Medium": Priority.STANDARD.value,
    "Low": Priority.ROUTINE.value,
}


def verify_severity_consistency(intel: CaseIntelligence, decision: str) -> Dict[str, Any]:
    expected_priority = _SEVERITY_PRIORITY_MAP.get(intel.severity, Priority.STANDARD.value)
    consistent = True
    notes: List[str] = []

    if intel.severity == "Critical" and decision not in (CaseDecision.EMERGENCY.value, CaseDecision.URGENT_ACTION.value):
        consistent = False
        notes.append(f"Severity is Critical but case decision is '{decision}'.")
    if intel.severity == "Low" and decision == CaseDecision.EMERGENCY.value:
        consistent = False
        notes.append("Severity is Low but case decision is Emergency.")

    if not notes:
        notes.append("Severity, risk score, and case decision are consistent.")

    return {"consistent": consistent, "expected_priority": expected_priority, "notes": notes}

# ## 13. Module 11 — Personalized Response Engine


_PERSONA_INTROS: Dict[Persona, str] = {
    Persona.GENERAL_CITIZEN: "Here is what you should do right now, explained simply:",
    Persona.SENIOR_CITIZEN: "Please follow these simple steps carefully. Take your time reading each one:",
    Persona.STUDENT: "Quick summary of what's going on and what to do next:",
    Persona.BUSINESS_OWNER: "This incident may affect your business accounts. Recommended steps:",
    Persona.BANK_EMPLOYEE: "Internal handling guidance for this reported case:",
    Persona.POLICE_OFFICER: "Case intelligence summary for investigation workflow:",
}


def personalize_response(persona: Persona, citizen_actions: List[str]) -> Dict[str, Any]:
    return {
        "persona": persona.value,
        "intro": _PERSONA_INTROS.get(persona, _PERSONA_INTROS[Persona.GENERAL_CITIZEN]),
        "actions": citizen_actions,
    }

# ## 14. Module 12 — Multilingual Generator


_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "Disconnect the call immediately": {
        "hi": "\u0924\u0941\u0930\u0902\u0924 \u0915\u0949\u0932 \u0915\u093e\u091f \u0926\u0947\u0902",
        "mr": "\u0924\u093e\u0924\u0921\u0940\u0928\u0947 \u0915\u0949\u0932 \u092c\u0902\u0926 \u0915\u0930\u093e",
    },
    "Do NOT transfer any money": {
        "hi": "\u0915\u094b\u0908 \u092d\u0940 \u092a\u0948\u0938\u093e \u091f\u094d\u0930\u093e\u0902\u0938\u092b\u0930 \u0928 \u0915\u0930\u0947\u0902",
        "mr": "\u0915\u094b\u0923\u0924\u0940\u0939\u0940 \u092a\u0948\u0938\u0947 \u091f\u094d\u0930\u093e\u0928\u094d\u0938\u092b\u0930 \u0915\u0930\u0942 \u0928\u0915\u093e",
    },
    "Report the incident on the 1930 helpline": {
        "hi": "1930 \u0939\u0947\u0932\u094d\u092a\u0932\u093e\u0907\u0928 \u092a\u0930 \u0938\u0942\u091a\u093f\u0924 \u0915\u0930\u0947\u0902",
        "mr": "1930 \u0939\u0947\u0932\u094d\u092a\u0932\u093e\u0907\u0928\u0935\u0930 \u0924\u0915\u094d\u0930\u093e\u0930 \u0926\u094d\u092f\u093e",
    },
    "Do not pay the demanded amount": {
        "hi": "\u092e\u093e\u0902\u0917\u0940 \u0917\u0908 \u0930\u093e\u0936\u093f \u0915\u093e \u092d\u0941\u0917\u0924\u093e\u0928 \u0928 \u0915\u0930\u0947\u0902",
        "mr": "\u092e\u093e\u0917\u0923\u0940 \u0915\u0947\u0932\u0947\u0932\u0940 \u0930\u0915\u094d\u0915\u092e \u0926\u0947\u090a \u0928\u0915\u093e",
    },
}


def generate_multilingual_response(citizen_actions: List[str], languages: Optional[List[str]] = None) -> Dict[str, List[str]]:
    languages = languages or CONFIG.DEFAULT_LANGUAGES
    output: Dict[str, List[str]] = {}
    for lang in languages:
        if lang == "en":
            output[lang] = list(citizen_actions)
            continue
        output[lang] = [_TRANSLATIONS.get(action, {}).get(lang, action) for action in citizen_actions]
    return output

# ## 15. Module 13 — Authority Mapping Engine


_AUTHORITY_MAP: Dict[str, List[str]] = {
    "Digital Arrest Scam": ["I4C / National Cyber Crime Reporting Portal (cybercrime.gov.in)", "1930 Cyber Crime Helpline", "Local Cyber Police Station"],
    "UPI / Payment Fraud": ["NPCI", "Citizen's Bank", "1930 Cyber Crime Helpline"],
    "Phishing / Credential Theft": ["1930 Cyber Crime Helpline", "Citizen's Bank"],
    "Extortion / Threat-based Fraud": ["Local Cyber Police Station", "1930 Cyber Crime Helpline"],
    "Investment Scam": ["SEBI", "Citizen's Bank"],
    "Counterfeit Currency": ["RBI", "Local Police Station"],
    "Identity Theft": ["UIDAI", "Local Cyber Police Station"],
}
_DEFAULT_AUTHORITY = ["1930 Cyber Crime Helpline", "cybercrime.gov.in"]


def map_authorities(intel: CaseIntelligence) -> List[str]:
    return _AUTHORITY_MAP.get(intel.fraud_type, _DEFAULT_AUTHORITY)

# ## 16. Module 14 — Evidence Packaging (+ Evidence Strength, feature 7)


# Which entity/indicator keys count as "evidence artifacts" for strength scoring.
_EVIDENCE_ARTIFACT_KEYS: Dict[str, int] = {
    "call_recording": 3,
    "voice": 3,
    "chat": 2,
    "screenshot": 2,
    "transaction": 3,
    "location": 1,
}


def package_evidence(intel: CaseIntelligence, timeline: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "case_id": intel.case_id,
        "fraud_type": intel.fraud_type,
        "indicators": intel.indicators,
        "unvalidated_indicators": intel.unvalidated_indicators,
        "entities": intel.entities,
        "citations": intel.evidence_citations,
        "reasoning_summary": intel.reasoning_summary,
        "confidence": intel.confidence,
        "risk_score": intel.risk_score,
        "timeline": timeline,
    }


def assess_evidence_strength(intel: CaseIntelligence) -> Dict[str, Any]:
    '''
    New (feature 7): rates evidence Weak / Moderate / Strong / Court Ready
    based on which artifact types Notebook 2 already found in `entities`
    (e.g. entities["evidence_artifacts"] = ["screenshot", "transaction"]),
    plus how many citations back the validated indicators. Deterministic
    point scale, not an LLM judgement call.
    '''
    artifacts = [a.lower() for a in intel.entities.get("evidence_artifacts", [])]
    score = sum(_EVIDENCE_ARTIFACT_KEYS.get(a, 1) for a in artifacts)
    score += min(len(intel.evidence_citations), 3)  # citations add modest weight, capped

    if score == 0:
        rating = EvidenceStrength.WEAK
    elif score <= 3:
        rating = EvidenceStrength.MODERATE
    elif score <= 6:
        rating = EvidenceStrength.STRONG
    else:
        rating = EvidenceStrength.COURT_READY

    return {
        "rating": rating.value,
        "artifacts_found": artifacts or ["(none reported)"],
        "score": score,
    }

# ## 17. Module 15 — Incident Report Generator


def generate_incident_report(
    intel: CaseIntelligence, decision: str, escalation: EscalationResult, authorities: List[str],
    case_status: Optional[str] = None, fraud_stage: Optional[str] = None,
    estimated_loss: Optional[str] = None,
) -> str:
    lines = [
        "INCIDENT REPORT",
        "=" * 40,
        f"Case ID          : {intel.case_id}",
        f"Timestamp        : {intel.timestamp}",
        f"Fraud Type       : {intel.fraud_type}",
        f"Severity         : {intel.severity}",
        f"Risk Score       : {intel.risk_score}/100",
        f"Confidence       : {intel.confidence}/100",
        f"Case Decision    : {decision}",
        f"Case Status      : {case_status or CaseStatus.DETECTED.value}",
        f"Fraud Stage      : {fraud_stage or FraudStage.UNKNOWN.value}",
        f"Estimated Loss   : {estimated_loss or 'Unknown'}",
        f"Escalated        : {'Yes (' + escalation.escalation_level + ')' if escalation.escalate else 'No'}",
        "",
        "Indicators Found:",
    ]
    lines += [f"  - {i}" for i in intel.indicators] or ["  (none)"]
    lines += [
        "",
        "Reasoning Summary:",
        f"  {intel.reasoning_summary or '(not provided)'}",
        "",
        "Recommended Authorities:",
    ]
    lines += [f"  - {a}" for a in authorities]
    lines += ["", "=" * 40]
    return "\n".join(lines)

# ## 18. Module 16 — Response Formatter


def format_response(package: Dict[str, Any], consumer: str) -> Any:
    if consumer == "citizen":
        actions = package["citizen_actions"]
        lines = ["Here's what to do:"] + [f"{i + 1}. {a}" for i, a in enumerate(actions)]
        lines.append(f"\nReport to: {', '.join(package['authorities'])}")
        return "\n".join(lines)

    if consumer == "police":
        return {
            "case_id": package["case_id"], "fraud_type": package["fraud_type"],
            "risk_score": package["risk_score"], "police_actions": package.get("police_actions", []),
            "evidence_package": package["evidence_package"], "incident_report": package["incident_report"],
            "fraud_stage": package["fraud_stage"], "case_status": package["case_status"],
        }

    if consumer == "bank":
        return {
            "case_id": package["case_id"], "fraud_type": package["fraud_type"],
            "bank_actions": package.get("bank_actions", []), "priority": package["priority"],
            "estimated_loss": package["estimated_loss"], "recovery_probability": package["recovery_probability"],
        }

    if consumer in ("dashboard", "api"):
        return package

    raise ValueError(f"Unknown response consumer: {consumer!r}")

# ## 19. Module 17 — Decision Audit Trail


def build_audit_trail(
    intel: CaseIntelligence,
    policy_result: Dict[str, Any],
    explainability: List[Dict[str, str]],
    escalation: EscalationResult,
) -> List[Dict[str, Any]]:
    trail: List[Dict[str, Any]] = [
        {
            "decision": policy_result["decision"],
            "reason": "; ".join(policy_result["policy_reasons"]),
            "based_on": {"risk_score": intel.risk_score, "confidence": intel.confidence, "fraud_type": intel.fraud_type},
            "policy_version": CONFIG.DECISION_POLICY_VERSION,
        }
    ]
    if escalation.escalate:
        trail.append({
            "decision": f"Escalate to {', '.join(escalation.escalate_to)}",
            "reason": escalation.reason,
            "based_on": {"risk_score": intel.risk_score, "confidence": intel.confidence},
            "policy_version": CONFIG.DECISION_POLICY_VERSION,
        })
    for entry in explainability:
        trail.append({
            "decision": f"[{entry['stakeholder']}] {entry['action']}",
            "reason": entry["reason"],
            "based_on": {"fraud_type": intel.fraud_type, "validated_indicators": intel.indicators},
            "policy_version": CONFIG.DECISION_POLICY_VERSION,
        })
    return trail


# ============================================================================
# 20. NEW — Case Management Layer
# (features 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 13)
# ============================================================================

# --- Feature 9: Fraud Pattern ID -------------------------------------------

_pattern_counters: Dict[str, int] = {}  # in-memory demo counter; real deployments use a DB sequence


def assign_pattern_id(fraud_type: str) -> str:
    '''New (feature 9): stable-looking pattern ID like DA-001, INV-007.'''
    prefix = CONFIG.PATTERN_ID_PREFIX.get(fraud_type, CONFIG.DEFAULT_PATTERN_PREFIX)
    _pattern_counters[prefix] = _pattern_counters.get(prefix, 0) + 1
    return f"{prefix}-{_pattern_counters[prefix]:03d}"


# --- Feature 2: Estimated Financial Loss ------------------------------------

def estimate_financial_loss(intel: CaseIntelligence) -> str:
    '''
    New (feature 2): passes through whatever amount Notebook 2 already
    extracted into entities["money_amounts"]. Notebook 3 does not invent a
    number — if Notebook 2 found nothing, this reports "Unknown".
    '''
    amounts = intel.entities.get("money_amounts", [])
    if not amounts:
        return "Unknown"
    return amounts[0] if len(amounts) == 1 else f"{amounts[0]} (+{len(amounts) - 1} more reference(s))"


def _money_was_transferred(intel: CaseIntelligence) -> Optional[bool]:
    '''Heuristic used by both fraud-stage and recovery scoring.'''
    if "Money Sent" in intel.indicators or intel.entities.get("transfer_confirmed"):
        return True
    if "Money Demand" in intel.indicators or "Urgent Payment Request" in intel.indicators:
        return False
    if intel.entities.get("money_amounts"):
        return None
    return None


# --- Feature 3: Fraud Stage --------------------------------------------------

# Ordered indicator -> stage mapping (later entries override earlier ones,
# i.e. the fraud stage reflects the FURTHEST point reached, not the first).
_STAGE_INDICATOR_MAP: List[Tuple[str, FraudStage]] = [
    ("Government Impersonation", FraudStage.CONTACT),
    ("Suspicious Link", FraudStage.CONTACT),
    ("OTP Request", FraudStage.CONTACT),
    ("Isolation Tactics", FraudStage.TRUST_BUILDING),
    ("Urgency", FraudStage.TRUST_BUILDING),
    ("Threat Language", FraudStage.THREAT),
    ("Criminal Allegation", FraudStage.THREAT),
    ("Blackmail / Extortion Threat", FraudStage.THREAT),
    ("Money Demand", FraudStage.MONEY_DEMAND),
    ("Urgent Payment Request", FraudStage.MONEY_DEMAND),
]

_STAGE_ORDER: List[FraudStage] = [
    FraudStage.CONTACT, FraudStage.TRUST_BUILDING, FraudStage.THREAT,
    FraudStage.MONEY_DEMAND, FraudStage.MONEY_SENT,
]


def determine_fraud_stage(intel: CaseIntelligence) -> Dict[str, Any]:
    '''New (feature 3): furthest stage reached, purely from validated indicators.'''
    reached = {FraudStage.CONTACT} if intel.indicators else set()
    for indicator, stage in _STAGE_INDICATOR_MAP:
        if indicator in intel.indicators:
            reached.add(stage)

    transferred = _money_was_transferred(intel)
    if transferred is True:
        reached.add(FraudStage.MONEY_SENT)

    if not reached:
        current = FraudStage.UNKNOWN
    else:
        current = max(reached, key=lambda s: _STAGE_ORDER.index(s) if s in _STAGE_ORDER else -1)

    return {
        "current_stage": current.value,
        "stages_observed": [s.value for s in _STAGE_ORDER if s in reached],
        "money_transferred": transferred,
    }


# --- Feature 6: Recovery Possibility Score ----------------------------------

def estimate_recovery_probability(intel: CaseIntelligence, money_transferred: Optional[bool]) -> Dict[str, Any]:
    '''New (feature 6): coarse, deterministic recovery-odds banding.'''
    if money_transferred is False:
        pct = CONFIG.RECOVERY_SCORE_NO_TRANSFER
        note = "No funds appear to have been transferred; recovery odds remain high if the citizen acts now."
    elif money_transferred is True:
        pct = CONFIG.RECOVERY_SCORE_TRANSFERRED
        note = "Funds appear to have been transferred; recovery depends on how quickly the bank/NPCI freeze the receiving account."
    else:
        pct = CONFIG.RECOVERY_SCORE_UNKNOWN
        note = "Transfer status is unconfirmed; recovery odds are a provisional midpoint estimate."
    return {"recovery_probability_pct": pct, "note": note}


# --- Feature 4: Victim Protection Score & Feature 11: Risk Reduction Simulator

def _classify_action_weight(action_text: str) -> int:
    '''Maps an action's text to a risk-reduction weight bucket (feature 11 helper).'''
    text = action_text.lower()
    if "disconnect" in text:
        return CONFIG.RISK_REDUCTION_WEIGHTS["disconnect"]
    if "do not transfer" in text or "do not pay" in text or "do not invest" in text or "do not transfer or reverse" in text:
        return CONFIG.RISK_REDUCTION_WEIGHTS["no_money"]
    if "otp" in text or "password" in text or "credential" in text or "aadhaar" in text or "pan" in text:
        return CONFIG.RISK_REDUCTION_WEIGHTS["no_otp_or_credentials"]
    if "report" in text or "file a complaint" in text or "register a" in text:
        return CONFIG.RISK_REDUCTION_WEIGHTS["report"]
    if "block" in text:
        return CONFIG.RISK_REDUCTION_WEIGHTS["block"]
    if "screenshot" in text or "preserve" in text or "evidence" in text or "recording" in text:
        return CONFIG.RISK_REDUCTION_WEIGHTS["evidence"]
    return 0


def simulate_risk_reduction(intel: CaseIntelligence, citizen_actions: List[StakeholderAction]) -> List[Dict[str, Any]]:
    '''
    New (feature 11): shows, action by action, how much the risk score would
    fall if the citizen completed each recommended step, in the fixed order
    the actions are already prioritized. Purely arithmetic — floors at 5.
    '''
    running_risk = intel.risk_score
    steps: List[Dict[str, Any]] = []
    for action in citizen_actions:
        weight = _classify_action_weight(action.action)
        new_risk = max(5, running_risk - weight)
        steps.append({
            "action": action.action,
            "risk_before": running_risk,
            "risk_after": new_risk,
        })
        running_risk = new_risk
    return steps


def calculate_victim_protection_score(
    intel: CaseIntelligence,
    citizen_actions: List[StakeholderAction],
    completed_action_ids: Optional[List[str]],
) -> Dict[str, Any]:
    '''
    New (feature 4): risk score "before" (Notebook 2's original risk_score)
    vs. "after" — computed only from the subset of citizen actions the
    citizen has actually marked complete (via completed_action_ids).
    '''
    completed_action_ids = set(completed_action_ids or [])
    risk_after = intel.risk_score
    for action in citizen_actions:
        if action.action_id in completed_action_ids:
            risk_after = max(5, risk_after - _classify_action_weight(action.action))

    return {
        "risk_before": intel.risk_score,
        "risk_after": risk_after,
        "risk_reduced_by": intel.risk_score - risk_after,
        "actions_completed": len(completed_action_ids & {a.action_id for a in citizen_actions}),
        "actions_total": len(citizen_actions),
    }


# --- Feature 5: Response Completion Tracker & Feature 13: Stakeholder Completion

def build_completion_tracker(
    prioritized_actions: Dict[str, List[StakeholderAction]],
    completed_action_ids: Optional[List[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    '''New (feature 5): per-action status, driven by an external
    completed_action_ids list (e.g. citizen ticking items in an app).
    Nothing is auto-marked complete by this notebook.'''
    completed_action_ids = set(completed_action_ids or [])
    tracker: Dict[str, List[Dict[str, Any]]] = {}
    for stakeholder, actions in prioritized_actions.items():
        tracker[stakeholder] = [
            {"action_id": a.action_id, "action": a.action, "completed": a.action_id in completed_action_ids}
            for a in actions
        ]
    return tracker


def build_stakeholder_completion(completion_tracker: Dict[str, List[Dict[str, Any]]]) -> Dict[str, str]:
    '''New (feature 13): rolls the per-action tracker up into a single
    Pending/Completed status per stakeholder.'''
    rollup: Dict[str, str] = {}
    for stakeholder, actions in completion_tracker.items():
        if actions and all(a["completed"] for a in actions):
            rollup[stakeholder] = "Completed"
        else:
            rollup[stakeholder] = "Pending"
    return rollup


# --- Feature 8: Notification Queue ------------------------------------------

def build_notification_queue(
    stakeholders: List[str],
    notification_updates: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    '''
    New (feature 8): every non-citizen stakeholder starts life as "Pending".
    `notification_updates` (e.g. {"Police": "Delivered"}) lets an external
    dispatch system report status back in; this notebook never marks its
    own notifications as sent — that's an integration's job.
    '''
    notification_updates = notification_updates or {}
    queue: Dict[str, str] = {}
    for s in stakeholders:
        if s == Stakeholder.CITIZEN.value:
            continue
        status = notification_updates.get(s, NotificationStatus.PENDING.value)
        try:
            NotificationStatus(status)  # validate
        except ValueError:
            status = NotificationStatus.PENDING.value
        queue[s] = status
    return queue


# --- Feature 1: Case Lifecycle -----------------------------------------------

def determine_case_status(
    decision: str,
    escalation: EscalationResult,
    notification_queue: Dict[str, str],
    override_status: Optional[str] = None,
) -> str:
    '''
    New (feature 1): if the caller (e.g. a case-management UI) supplies an
    explicit `override_status`, that wins — this notebook is a state
    *reporter*, not the sole owner of case status. Otherwise it derives a
    reasonable default from decision + notification progress so a freshly
    processed case always starts somewhere sensible on the lifeline.
    '''
    if override_status:
        try:
            return CaseStatus(override_status).value
        except ValueError:
            logger.warning("Unknown case_status override %r; falling back to derived status.", override_status)

    if decision == CaseDecision.NO_ACTION.value:
        return CaseStatus.CLOSED.value
    if not notification_queue:
        return CaseStatus.DETECTED.value
    if any(v != NotificationStatus.PENDING.value for v in notification_queue.values()):
        return CaseStatus.REPORTED.value
    if escalation.escalate:
        return CaseStatus.UNDER_INVESTIGATION.value
    return CaseStatus.DETECTED.value


# --- Feature 10: Similar Previous Cases --------------------------------------

def format_similar_cases(similar_cases: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    '''
    New (feature 10): pure pass-through/formatting of whatever Notebook 2's
    RAG layer already retrieved (e.g. [{"case_id": "case-13", "similarity": 0.94}, ...]).
    Notebook 3 performs NO retrieval itself — no vector store access here.
    '''
    if not similar_cases:
        return []
    formatted = []
    for c in similar_cases:
        formatted.append({
            "case_id": c.get("case_id", "unknown"),
            "similarity_pct": round(float(c.get("similarity", 0)) * 100, 1)
                if isinstance(c.get("similarity"), float) and c.get("similarity") <= 1
                else c.get("similarity", 0),
        })
    return sorted(formatted, key=lambda c: c["similarity_pct"], reverse=True)

# ## 21. Orchestration — Final Decision Package


def build_decision_package(
    notebook2_output: Dict[str, Any],
    persona: Persona = Persona.GENERAL_CITIZEN,
    languages: Optional[List[str]] = None,
    completed_action_ids: Optional[List[str]] = None,
    notification_updates: Optional[Dict[str, str]] = None,
    case_status_override: Optional[str] = None,
    similar_cases: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    '''
    Notebook 3 orchestration.

    New optional params (all pass-through / external-state inputs, never
    generated by this notebook):
      completed_action_ids  - citizen-ticked action_ids, drives features 4 & 5
      notification_updates  - external dispatch status, drives feature 8
      case_status_override  - external case-management status, drives feature 1
      similar_cases         - Notebook 2's RAG neighbours, drives feature 10
    '''
    try:
        intel = parse_intelligence(notebook2_output)

        policy_result = determine_case_decision(intel)
        decision = policy_result["decision"]

        stakeholders = identify_stakeholders(intel, decision)
        matrix = build_decision_matrix(intel, stakeholders)
        prioritized = prioritize_actions(matrix)
        timeline = generate_timeline(prioritized)
        escalation = determine_escalation(intel, decision)
        recommendations = generate_recommendations(prioritized)
        explainability = build_explainability_report(prioritized)
        explanation_card = build_explanation_card(intel, decision)
        severity_check = verify_severity_consistency(intel, decision)
        authorities = map_authorities(intel)
        evidence_package = package_evidence(intel, timeline)
        evidence_strength = assess_evidence_strength(intel)

        citizen_actions_objs = prioritized.get(Stakeholder.CITIZEN.value, [])
        citizen_actions = recommendations.get(Stakeholder.CITIZEN.value, [])
        personalized = personalize_response(persona, citizen_actions)
        multilingual = generate_multilingual_response(citizen_actions, languages)
        audit_trail = build_audit_trail(intel, policy_result, explainability, escalation)

        # --- Case Management Layer ---
        pattern_id = assign_pattern_id(intel.fraud_type)
        estimated_loss = estimate_financial_loss(intel)
        fraud_stage_info = determine_fraud_stage(intel)
        recovery_info = estimate_recovery_probability(intel, fraud_stage_info["money_transferred"])
        protection_score = calculate_victim_protection_score(intel, citizen_actions_objs, completed_action_ids)
        risk_simulation = simulate_risk_reduction(intel, citizen_actions_objs)
        completion_tracker = build_completion_tracker(prioritized, completed_action_ids)
        stakeholder_completion = build_stakeholder_completion(completion_tracker)
        notification_queue = build_notification_queue(stakeholders, notification_updates)
        case_status = determine_case_status(decision, escalation, notification_queue, case_status_override)
        similar_cases_formatted = format_similar_cases(similar_cases)

        incident_report = generate_incident_report(
            intel, decision, escalation, authorities,
            case_status=case_status, fraud_stage=fraud_stage_info["current_stage"],
            estimated_loss=estimated_loss,
        )

        overall_priority = min(
            (a.priority for actions in prioritized.values() for a in actions),
            key=lambda p: _PRIORITY_ORDER.get(p, 99),
            default=Priority.ROUTINE.value,
        )

        package: Dict[str, Any] = {
            # --- Identity ---
            "case_id": intel.case_id,
            "pattern_id": pattern_id,
            "timestamp": intel.timestamp,
            "fraud_type": intel.fraud_type,
            "decision_policy_version": CONFIG.DECISION_POLICY_VERSION,

            # --- Core decision (unchanged) ---
            "case_decision": decision,
            "policy_reasons": policy_result["policy_reasons"],
            "priority": overall_priority,
            "severity_check": severity_check,
            "stakeholders": stakeholders,
            "citizen_actions": citizen_actions,
            "bank_actions": recommendations.get(Stakeholder.BANK.value, []),
            "telecom_actions": recommendations.get(Stakeholder.TELECOM.value, []),
            "police_actions": recommendations.get(Stakeholder.POLICE.value, []),
            "other_actions": {
                k: v for k, v in recommendations.items()
                if k not in (Stakeholder.CITIZEN.value, Stakeholder.BANK.value, Stakeholder.TELECOM.value, Stakeholder.POLICE.value)
            },
            "timeline": timeline,
            "escalation": {
                "escalate": escalation.escalate, "level": escalation.escalation_level,
                "escalate_to": escalation.escalate_to, "reason": escalation.reason,
            },
            "authorities": authorities,
            "personalized_response": personalized,
            "multilingual_response": multilingual,
            "explainability": explainability,
            "explanation_card": explanation_card,
            "evidence_package": evidence_package,
            "incident_report": incident_report,
            "audit_trail": audit_trail,

            # --- New: Case Management Layer ---
            "case_status": case_status,
            "fraud_stage": fraud_stage_info["current_stage"],
            "fraud_stage_detail": fraud_stage_info,
            "estimated_loss": estimated_loss,
            "recovery_probability": recovery_info,
            "evidence_strength": evidence_strength,
            "victim_protection_score": protection_score,
            "risk_reduction_simulation": risk_simulation,
            "response_completion_tracker": completion_tracker,
            "stakeholder_completion": stakeholder_completion,
            "notification_queue": notification_queue,
            "similar_previous_cases": similar_cases_formatted,
        }

        logger.info(
            "Decision package built for case %s (%s). decision=%s priority=%s stage=%s status=%s escalate=%s",
            intel.case_id, pattern_id, decision, overall_priority,
            fraud_stage_info["current_stage"], case_status, escalation.escalate,
        )
        return package

    except DecisionIntelligenceError:
        raise
    except Exception as exc:
        logger.exception("Failed to build decision package.")
        raise DecisionIntelligenceError(f"Notebook 3 pipeline failed: {exc}") from exc

# ## 22. Sample Inputs


SAMPLE_NOTEBOOK2_OUTPUTS: List[Tuple[str, Dict[str, Any]]] = [
    (
        "digital_arrest_critical",
        {
            "case_id": "case-da-001",
            "fraud_type": "Digital Arrest Scam",
            "risk_score": 95,
            "confidence": 92,
            "severity": "Critical",
            "indicators": ["Government Impersonation", "Criminal Allegation", "Isolation Tactics", "Urgent Payment Request"],
            "unvalidated_indicators": [],
            "entities": {
                "money_amounts": ["Rs 2,00,000"],
                "evidence_artifacts": ["call_recording", "screenshot"],
            },
            "citations": {"Government Impersonation": [0, 2]},
            "summary": "Caller claimed to be from CBI, alleged money laundering, and demanded urgent payment while discouraging the citizen from disconnecting.",
            "timestamp": "2026-07-12T10:00:00+00:00",
        },
    ),
    (
        "upi_fraud_medium",
        {
            "case_id": "case-upi-001",
            "fraud_type": "UPI / Payment Fraud",
            "risk_score": 55,
            "confidence": 78,
            "severity": "Medium",
            "indicators": ["OTP Request", "Urgent Payment Request"],
            "unvalidated_indicators": [],
            "entities": {"upi_ids": ["rahul.verify@upi"], "evidence_artifacts": ["chat"]},
            "citations": {},
            "summary": "Sender claimed a mistaken UPI transfer and requested OTP and reversal.",
            "timestamp": "2026-07-12T10:05:00+00:00",
        },
    ),
    (
        "extortion_high",
        {
            "case_id": "case-ext-001",
            "fraud_type": "Extortion / Threat-based Fraud",
            "risk_score": 70,
            "confidence": 81,
            "severity": "High",
            "indicators": ["Blackmail / Extortion Threat", "Threat Language"],
            "unvalidated_indicators": [],
            "entities": {"money_amounts": ["Rs 50,000"], "evidence_artifacts": ["screenshot", "chat"]},
            "citations": {},
            "summary": "Sender claimed to possess private photos and threatened to leak them unless paid.",
            "timestamp": "2026-07-12T10:10:00+00:00",
        },
    ),
    (
        "benign_case",
        {
            "case_id": "case-benign-001",
            "fraud_type": "Unclassified Suspicious Activity",
            "risk_score": 0,
            "confidence": 60,
            "severity": "Low",
            "indicators": [],
            "unvalidated_indicators": [],
            "entities": {},
            "citations": {},
            "summary": "No fraud indicators identified.",
            "timestamp": "2026-07-12T10:15:00+00:00",
        },
    ),
    (
        "low_confidence_ambiguous",
        {
            "case_id": "case-amb-001",
            "fraud_type": "Unclassified Suspicious Activity",
            "risk_score": 20,
            "confidence": 35,
            "severity": "Low",
            "indicators": [],
            "unvalidated_indicators": ["possible scam reference"],
            "entities": {},
            "citations": {},
            "summary": "Insufficient evidence to reach a confident conclusion.",
            "timestamp": "2026-07-12T10:20:00+00:00",
        },
    ),
]

# ## 23. Deterministic Test Suite


def _check(label: str, actual: Any, expected: Any) -> bool:
    ok = actual == expected
    print(f"    [{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")
    return ok


EXPECTED: Dict[str, Dict[str, Any]] = {
    "digital_arrest_critical": {
        "case_decision": "Emergency", "escalate": True, "escalation_level": "Emergency",
        "fraud_stage": "Money Demand", "money_transferred": False,
    },
    "upi_fraud_medium": {
        "case_decision": "Urgent Action", "escalate": False, "escalation_level": "None",
        "fraud_stage": "Money Demand", "money_transferred": False,
    },
    "extortion_high": {
        "case_decision": "Urgent Action", "escalate": False, "escalation_level": "None",
        "fraud_stage": "Threat", "money_transferred": None,
    },
    "benign_case": {
        "case_decision": "No Action - Benign", "escalate": False, "escalation_level": "None",
        "fraud_stage": "Unknown", "money_transferred": None,
    },
    "low_confidence_ambiguous": {
        "case_decision": "Needs Human Review", "escalate": True, "escalation_level": "Standard",
        "fraud_stage": "Unknown", "money_transferred": None,
    },
}


def run_notebook3_test_suite() -> Dict[str, Any]:
    total = 0
    passed = 0
    results: Dict[str, Any] = {}

    for name, n2_output in SAMPLE_NOTEBOOK2_OUTPUTS:
        print(f"\n=== {name} ===")
        try:
            # Demo: mark the "disconnect" and "block" actions complete for the
            # critical case, to exercise the completion tracker / protection score.
            completed = ["citizen-00", "citizen-05"] if name == "digital_arrest_critical" else None
            package = build_decision_package(n2_output, completed_action_ids=completed)
        except DecisionIntelligenceError as exc:
            print(f"    [FAIL] build_decision_package raised an error: {exc}")
            results[name] = {"error": str(exc)}
            total += 1
            continue

        results[name] = package
        expected = EXPECTED[name]
        checks = [
            _check("case_decision", package["case_decision"], expected["case_decision"]),
            _check("escalation.escalate", package["escalation"]["escalate"], expected["escalate"]),
            _check("escalation.level", package["escalation"]["level"], expected["escalation_level"]),
            _check("fraud_stage", package["fraud_stage"], expected["fraud_stage"]),
            _check("money_transferred", package["fraud_stage_detail"]["money_transferred"], expected["money_transferred"]),
        ]
        total += len(checks)
        passed += sum(checks)

        print(f"    pattern_id={package['pattern_id']} case_status={package['case_status']} priority={package['priority']}")
        print(f"    estimated_loss={package['estimated_loss']} recovery={package['recovery_probability']['recovery_probability_pct']}%")
        print(f"    evidence_strength={package['evidence_strength']['rating']}")
        print(f"    victim_protection_score={package['victim_protection_score']}")
        print(f"    stakeholders={package['stakeholders']}")
        print(f"    stakeholder_completion={package['stakeholder_completion']}")
        print(f"    notification_queue={package['notification_queue']}")
        print(f"    severity_check={package['severity_check']['notes']}")

    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} checks passed across {len(SAMPLE_NOTEBOOK2_OUTPUTS)} cases")
    print("=" * 60)
    return results


if __name__ == "__main__":
    all_packages = run_notebook3_test_suite()

    # ------------------------------------------------------------------
    # Demo — Full Decision Package for the Critical Case
    # ------------------------------------------------------------------
    demo_package = all_packages["digital_arrest_critical"]

    print("\n" + "#" * 60)
    print("DEMO: Digital Arrest Scam — full decision package")
    print("#" * 60)

    print(format_response(demo_package, "citizen"))
    print()
    print(demo_package["incident_report"])
    print()
    print("Explanation card:")
    print(json.dumps(demo_package["explanation_card"], indent=2, ensure_ascii=False))
    print()
    print("Risk reduction simulation (citizen actions, in order):")
    for step in demo_package["risk_reduction_simulation"]:
        print(f"  {step['risk_before']:>3} -> {step['risk_after']:>3}  after: {step['action']}")
    print()
    print("Audit trail (first 6 entries):")
    for entry in demo_package["audit_trail"][:6]:
        print(f"  - {entry['decision']}  <-  {entry['reason']}")
    print()
    print("Multilingual citizen actions (Hindi):")
    for action in demo_package["multilingual_response"]["hi"]:
        print(f"  - {action}")