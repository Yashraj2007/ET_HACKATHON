# Generated from: fraud_network_intelligence_engine.ipynb
# Converted at: 2026-07-15T01:44:20.727Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # Fraud Network Intelligence Engine
# 
# fraud_network_intelligence_engine.py
# ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)
# Notebook 6 - Fraud Network Intelligence Engine (Revision 1)
# 
# Mission (one sentence):
# Take individually-scored fraud cases from Notebook 2 and discover the
# hidden network that connects them - shared phones, UPI IDs, emails,
# devices, bank accounts - so that isolated complaints become a single,
# explainable intelligence package a police unit can act on.
# 
# What this notebook is NOT:
#   - It does not classify a case as fraud or not. That is Notebook 2's job.
#   - It does not verify currency images. That is Notebook 5's job.
#   - It does not decide the final action to take. That is Notebook 3's job.
#   - It is not a visualization notebook. The graph picture is one output
#     among many; the real product is the network intelligence package.
# 
# Position in the pipeline (per the architectural note in the design
# discussion for this notebook):
# 
#   Citizen report / evidence
#           |
#           v
#   Notebook 2 - Fraud Intelligence Engine  (per-case risk score)
#           |
#           v
#   Notebook 6 - Fraud Network Intelligence Engine   <- this file
#     (links the new case into the shared graph, raises or confirms risk
#      using what the network already knows)
#           |
#           v
#   Notebook 3 - Decision Intelligence Engine  (uses the network-adjusted
#      risk score, not just the standalone one, to decide the final action)
# 
# Design approach:
# Every case is decomposed into entities (phone, UPI, email, bank account,
# device, IMEI, IP, wallet, URL/domain, organization, victim). Entities are
# normalized so the same phone number or email reported by two different
# citizens collapses to one node (Duplicate Entity Resolver). Entities are
# connected using a small set of named, explainable relationships (e.g.
# "used_upi", "registered_email") rather than a black-box embedding, so
# every edge in the final graph can be read out loud to an investigator.
# Community detection, money-mule heuristics, central-actor ranking, and
# risk propagation are then run on top of that explainable graph.
# 
# This notebook builds and analyzes the network with the standard
# `networkx` graph library. Visualization uses `matplotlib` when available
# and degrades gracefully (skips image export, keeps all other analysis)
# when it is not, since network analysis must not depend on a plotting
# backend being installed.


import hashlib
import itertools
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

try:
    import matplotlib
    matplotlib.use("Agg")  # headless rendering, no display server required
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False

try:
    from networkx.algorithms.community import greedy_modularity_communities
    _COMMUNITY_ALGO_AVAILABLE = True
except ImportError:
    _COMMUNITY_ALGO_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("fraud_network_intelligence_engine")

# ## 1. Configuration


class Config:
    '''Central configuration for Notebook 6.'''

    NOTEBOOK_VERSION = "v1.0"

    # --- Module 7: Money mule detection thresholds ---
    MULE_MIN_DISTINCT_VICTIMS = 3       # a financial entity linked to >= this many victims is suspicious
    MULE_MIN_DISTINCT_CASES = 2         # and must appear across >= this many separate cases
    MULE_SCORE_VICTIM_WEIGHT = 0.6
    MULE_SCORE_CASE_WEIGHT = 0.4

    # --- Module 6: Community detection ---
    COMMUNITY_MIN_SIZE = 2              # communities smaller than this are not reported as a ring

    # --- Module 8: Central actor detection (weights must sum to 1.0) ---
    CENTRALITY_DEGREE_WEIGHT = 0.35
    CENTRALITY_BETWEENNESS_WEIGHT = 0.35
    CENTRALITY_PAGERANK_WEIGHT = 0.30
    CENTRAL_ACTOR_TOP_K = 5

    # --- Module 6: Community risk / priority thresholds ---
    COMMUNITY_PRIORITY_CRITICAL_MIN = 85.0
    COMMUNITY_PRIORITY_HIGH_MIN = 70.0
    COMMUNITY_PRIORITY_MEDIUM_MIN = 50.0

    # --- Module 10: Campaign activity window ---
    CAMPAIGN_ACTIVE_WINDOW_DAYS = 30    # a campaign with no activity within this window is "Dormant"

    # --- Module 12: Risk propagation ---
    RISK_PROPAGATION_ITERATIONS = 3
    RISK_PROPAGATION_DECAY = 0.55       # how much of a neighbor's risk carries over per hop
    RISK_PROPAGATION_MAX_BOOST = 25.0   # a case's risk can be raised by at most this many points

    # --- Entity types that participate in graph analytics (case nodes are
    # excluded from centrality / community / mule computations because a
    # case node is, by construction, connected to every entity in that
    # case and would otherwise read as an artificial hub). ---
    ANALYTIC_NODE_TYPES = {
        "phone", "upi", "email", "bank_account", "device_id", "imei",
        "ip", "wallet_id", "url", "domain", "organization", "victim",
    }
    FINANCIAL_NODE_TYPES = {"upi", "bank_account", "wallet_id"}


CONFIG = Config()
assert abs(
    CONFIG.CENTRALITY_DEGREE_WEIGHT + CONFIG.CENTRALITY_BETWEENNESS_WEIGHT + CONFIG.CENTRALITY_PAGERANK_WEIGHT - 1.0
) < 1e-6, "Central actor centrality weights must sum to 1.0."
logger.info("Notebook 6 configuration loaded. version=%s", CONFIG.NOTEBOOK_VERSION)

# ## 2. Core Enums and Exceptions


class EntityType(str, Enum):
    PHONE = "phone"
    UPI = "upi"
    EMAIL = "email"
    BANK_ACCOUNT = "bank_account"
    DEVICE_ID = "device_id"
    IMEI = "imei"
    IP = "ip"
    WALLET_ID = "wallet_id"
    URL = "url"
    DOMAIN = "domain"
    ORGANIZATION = "organization"
    VICTIM = "victim"
    CASE = "case"


class FraudNetworkIntelligenceError(Exception):
    '''Raised when Notebook 6 cannot produce a valid network intelligence package.'''

# ## 3. Input Contract - Case Record
# 
# A CaseRecord is the shape Notebook 6 expects to receive from Notebook 2
# (plus whatever raw entities Notebook 4 already pulled out of the
# evidence). Notebook 6 does not compute risk_score or fraud_type itself -
# those are Notebook 2's outputs, taken here as given.


@dataclass
class CaseRecord:
    case_id: str
    victim_id: Optional[str] = None
    fraud_type: Optional[str] = None
    risk_score: float = 0.0
    phone_numbers: List[str] = field(default_factory=list)
    upi_ids: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    bank_accounts: List[str] = field(default_factory=list)
    device_ids: List[str] = field(default_factory=list)
    imeis: List[str] = field(default_factory=list)
    ips: List[str] = field(default_factory=list)
    wallet_ids: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    organizations: List[str] = field(default_factory=list)
    amount_involved: float = 0.0
    city: Optional[str] = None
    state: Optional[str] = None
    timestamp: Optional[str] = None
    # Optional fine-grained event log for this case, e.g.
    # [{"event": "Call received", "timestamp": "2026-07-01T10:02:00+00:00"}, ...].
    # Used only by Module 16 (Timeline Reconstruction); every other module
    # ignores this field, so cases without an event log still work.
    events: List[Dict[str, str]] = field(default_factory=list)

# ## 4. Module 5 (applied early) - Entity Normalization / Duplicate Resolver
# 
# Normalization happens once, here, before any node is ever created. Every
# other module downstream only ever sees normalized values, so "the same
# phone number reported twice" or "Rahul@gmail.com" vs "rahul@gmail.com"
# collapse into a single node by construction rather than needing a
# separate reconciliation pass later.


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits[-10:] if len(digits) >= 10 else digits


def _normalize_generic(value: str) -> str:
    return value.strip().lower()


_NORMALIZERS = {
    EntityType.PHONE.value: _normalize_phone,
    EntityType.UPI.value: _normalize_generic,
    EntityType.EMAIL.value: _normalize_generic,
    EntityType.BANK_ACCOUNT.value: lambda v: re.sub(r"\s", "", v).upper(),
    EntityType.DEVICE_ID.value: _normalize_generic,
    EntityType.IMEI.value: lambda v: re.sub(r"\D", "", v),
    EntityType.IP.value: _normalize_generic,
    EntityType.WALLET_ID.value: _normalize_generic,
    EntityType.URL.value: _normalize_generic,
    EntityType.DOMAIN.value: _normalize_generic,
    EntityType.ORGANIZATION.value: _normalize_generic,
    EntityType.VICTIM.value: _normalize_generic,
}


def node_id(entity_type: str, raw_value: str) -> str:
    '''Builds the canonical node id "type:normalized_value" used everywhere in the graph.'''
    normalizer = _NORMALIZERS.get(entity_type, _normalize_generic)
    return f"{entity_type}:{normalizer(raw_value)}"

# ## 5. Module 1 - Entity Collector


_CASE_FIELD_TO_ENTITY_TYPE: Dict[str, str] = {
    "phone_numbers": EntityType.PHONE.value,
    "upi_ids": EntityType.UPI.value,
    "emails": EntityType.EMAIL.value,
    "bank_accounts": EntityType.BANK_ACCOUNT.value,
    "device_ids": EntityType.DEVICE_ID.value,
    "imeis": EntityType.IMEI.value,
    "ips": EntityType.IP.value,
    "wallet_ids": EntityType.WALLET_ID.value,
    "urls": EntityType.URL.value,
    "domains": EntityType.DOMAIN.value,
    "organizations": EntityType.ORGANIZATION.value,
}


def collect_entities_from_case(case: CaseRecord) -> Dict[str, List[str]]:
    '''
    Module 1 entry point. Pulls every typed entity list off a CaseRecord
    and returns them keyed by entity type, each entry already de-duplicated
    within the case. The victim itself is included as an entity of type
    "victim" when a victim_id is present, since the citizen is a node in
    the network just as much as the phone number that called them.
    '''
    entities: Dict[str, List[str]] = defaultdict(list)

    for field_name, entity_type in _CASE_FIELD_TO_ENTITY_TYPE.items():
        raw_values = getattr(case, field_name) or []
        seen: Set[str] = set()
        for raw in raw_values:
            if not raw:
                continue
            normalized = _NORMALIZERS[entity_type](raw)
            if normalized and normalized not in seen:
                seen.add(normalized)
                entities[entity_type].append(raw)

    if case.victim_id:
        entities[EntityType.VICTIM.value] = [case.victim_id]

    return dict(entities)

# ## 6. Module 3 - Relationship Builder (semantic, explainable edges)
# 
# Only a small, named set of relationships is used, deliberately, so that
# every edge can be read out to an investigator as a plain sentence
# ("this phone used this UPI ID") instead of an opaque similarity score.


_EXPLICIT_RELATIONS: List[Tuple[str, str, str]] = [
    (EntityType.VICTIM.value, EntityType.PHONE.value, "received_call_from"),
    (EntityType.VICTIM.value, EntityType.EMAIL.value, "received_email_from"),
    (EntityType.PHONE.value, EntityType.DEVICE_ID.value, "belongs_to"),
    (EntityType.DEVICE_ID.value, EntityType.IMEI.value, "has_imei"),
    (EntityType.PHONE.value, EntityType.IP.value, "accessed_from"),
    (EntityType.PHONE.value, EntityType.UPI.value, "used_upi"),
    (EntityType.UPI.value, EntityType.EMAIL.value, "registered_email"),
    (EntityType.UPI.value, EntityType.WALLET_ID.value, "linked_wallet"),
    (EntityType.UPI.value, EntityType.BANK_ACCOUNT.value, "linked_account"),
    (EntityType.BANK_ACCOUNT.value, EntityType.ORGANIZATION.value, "held_at"),
    (EntityType.URL.value, EntityType.DOMAIN.value, "hosted_on"),
]

# ## 7. Module 2 + Module 4 - Node Builder & Graph Storage


class FraudNetworkGraph:
    '''
    Module 2 (Node Builder) and Module 4 (Graph Storage) combined into one
    thin wrapper around networkx. A directed multigraph is kept as the
    source of truth so that multiple distinct relations between the same
    pair of entities (e.g. two different cases both saying "phone used
    this UPI") are preserved for audit purposes. All analytics (Modules
    6-8, 12) run on an undirected simple-graph view derived from it, since
    community detection and centrality are undirected concepts and a
    de-duplicated view avoids double-counting parallel edges.
    '''

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()
        self.cases: Dict[str, CaseRecord] = {}
        # node_id -> set of case_ids that touched this entity; kept as a
        # direct attribute rather than only being derivable via graph
        # traversal, so cross-case matching (Module 9) stays O(1) per node
        # instead of walking through a potential case-node hub.
        self.entity_cases: Dict[str, Set[str]] = defaultdict(set)

    def add_node(self, nid: str, entity_type: str, label: str) -> None:
        if nid not in self.graph:
            self.graph.add_node(nid, entity_type=entity_type, label=label)

    def add_edge(self, source: str, target: str, relation: str, case_id: str) -> None:
        self.graph.add_edge(source, target, relation=relation, case_id=case_id)

    def link_case(self, node_id_: str, case_id: str) -> None:
        self.entity_cases[node_id_].add(case_id)

    def undirected_view(self, exclude_types: Optional[Set[str]] = None) -> nx.Graph:
        '''Builds the simple undirected analytics graph, optionally excluding node types.'''
        exclude_types = exclude_types or set()
        simple = nx.Graph()
        for nid, attrs in self.graph.nodes(data=True):
            if attrs.get("entity_type") in exclude_types:
                continue
            simple.add_node(nid, **attrs)
        for u, v, attrs in self.graph.edges(data=True):
            if u in simple.nodes and v in simple.nodes:
                simple.add_edge(u, v, relation=attrs.get("relation"))
        return simple

    def node_count(self) -> int:
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        return self.graph.number_of_edges()


def ingest_case_into_graph(fng: FraudNetworkGraph, case: CaseRecord) -> Dict[str, List[str]]:
    '''
    Runs Modules 1-3 for a single case: collects its entities, adds a node
    per distinct normalized entity plus a node for the case itself, wires
    up the explicit semantic relations that apply, and links every
    resulting node back to this case_id for later cross-case matching.
    Returns the entity dict (raw values, keyed by type) for audit display.
    '''
    fng.cases[case.case_id] = case
    entities = collect_entities_from_case(case)

    case_node = node_id(EntityType.CASE.value, case.case_id)
    fng.add_node(case_node, EntityType.CASE.value, case.case_id)
    fng.link_case(case_node, case.case_id)

    # Node Builder: one node per normalized entity, plus a "documented_in"
    # edge back to the case node so the case's full entity set can always
    # be reconstructed even if no semantic relation happens to connect
    # two particular entity types directly.
    normalized_by_type: Dict[str, List[str]] = {}
    for entity_type, raw_values in entities.items():
        normalized_values = []
        for raw in raw_values:
            normalized = _NORMALIZERS[entity_type](raw)
            nid = node_id(entity_type, raw)
            fng.add_node(nid, entity_type, raw)
            fng.add_edge(case_node, nid, "documented_in", case.case_id)
            fng.link_case(nid, case.case_id)
            normalized_values.append(normalized)
        normalized_by_type[entity_type] = normalized_values

    # Relationship Builder: connect entity types per the explicit relation
    # table wherever both sides are present in this case.
    for type_a, type_b, relation in _EXPLICIT_RELATIONS:
        values_a = entities.get(type_a, [])
        values_b = entities.get(type_b, [])
        for raw_a, raw_b in itertools.product(values_a, values_b):
            node_a = node_id(type_a, raw_a)
            node_b = node_id(type_b, raw_b)
            fng.add_edge(node_a, node_b, relation, case.case_id)

    return entities

# ## 8. Module 6 - Community Detection


def detect_communities(fng: FraudNetworkGraph) -> List[Dict[str, Any]]:
    '''
    Module 6 entry point. Groups the entity/victim graph (case nodes
    excluded, see Config.ANALYTIC_NODE_TYPES) into communities using
    greedy modularity maximization, falling back to plain connected
    components if the modularity algorithm is unavailable or the graph is
    too small for it to run meaningfully.
    '''
    analytic_graph = fng.undirected_view(exclude_types={EntityType.CASE.value})
    if analytic_graph.number_of_nodes() == 0:
        return []

    if _COMMUNITY_ALGO_AVAILABLE and analytic_graph.number_of_edges() > 0:
        try:
            raw_communities = list(greedy_modularity_communities(analytic_graph))
        except Exception as exc:
            logger.warning("Modularity community detection failed, falling back to connected components: %s", exc)
            raw_communities = list(nx.connected_components(analytic_graph))
    else:
        raw_communities = list(nx.connected_components(analytic_graph))

    communities: List[Dict[str, Any]] = []
    for idx, members in enumerate(sorted(raw_communities, key=len, reverse=True), start=1):
        if len(members) < CONFIG.COMMUNITY_MIN_SIZE:
            continue
        member_list = sorted(members)
        case_ids: Set[str] = set()
        for m in member_list:
            case_ids |= fng.entity_cases.get(m, set())
        fraud_types = [
            fng.cases[cid].fraud_type for cid in case_ids
            if cid in fng.cases and fng.cases[cid].fraud_type
        ]
        dominant_fraud = max(set(fraud_types), key=fraud_types.count) if fraud_types else "Unclassified"

        case_risk_scores = [fng.cases[cid].risk_score for cid in case_ids if cid in fng.cases]
        community_risk = round(sum(case_risk_scores) / len(case_risk_scores), 1) if case_risk_scores else 0.0
        if community_risk >= CONFIG.COMMUNITY_PRIORITY_CRITICAL_MIN:
            priority = "Critical"
        elif community_risk >= CONFIG.COMMUNITY_PRIORITY_HIGH_MIN:
            priority = "High"
        elif community_risk >= CONFIG.COMMUNITY_PRIORITY_MEDIUM_MIN:
            priority = "Medium"
        else:
            priority = "Low"

        # Confidence grows with how much corroborating evidence backs the
        # community: more linked cases and more shared entities both make
        # "this is one ring" a stronger claim than a two-case, two-entity guess.
        case_support = min(1.0, len(case_ids) / 5.0)
        size_support = min(1.0, len(member_list) / 8.0)
        confidence = round(min(99.0, 100 * (0.6 * case_support + 0.4 * size_support)), 1)

        communities.append({
            "community_id": f"COMM-{idx:02d}",
            "size": len(member_list),
            "members": member_list,
            "connected_cases": sorted(case_ids),
            "dominant_fraud": dominant_fraud,
            "community_risk": community_risk,
            "priority": priority,
            "confidence": confidence,
        })

    logger.info("Community detection complete. communities_found=%d", len(communities))
    return communities

# ## 9. Module 7 - Money Mule Detection


def detect_money_mules(fng: FraudNetworkGraph) -> List[Dict[str, Any]]:
    '''
    Module 7 entry point. Flags financial entities (UPI IDs, bank
    accounts, wallets) that receive money on behalf of an unusually large
    and diverse set of victims/cases - the classic money-mule signature -
    rather than trying to trace the actual transaction ledger, which this
    notebook does not have access to.
    '''
    analytic_graph = fng.undirected_view(exclude_types={EntityType.CASE.value})
    mules: List[Dict[str, Any]] = []

    for nid, attrs in analytic_graph.nodes(data=True):
        if attrs.get("entity_type") not in CONFIG.FINANCIAL_NODE_TYPES:
            continue

        case_ids = fng.entity_cases.get(nid, set())
        distinct_victims: Set[str] = set()
        for cid in case_ids:
            case = fng.cases.get(cid)
            if case and case.victim_id:
                distinct_victims.add(_normalize_generic(case.victim_id))

        if (
            len(distinct_victims) >= CONFIG.MULE_MIN_DISTINCT_VICTIMS
            and len(case_ids) >= CONFIG.MULE_MIN_DISTINCT_CASES
        ):
            victim_component = min(1.0, len(distinct_victims) / max(1, CONFIG.MULE_MIN_DISTINCT_VICTIMS * 2))
            case_component = min(1.0, len(case_ids) / max(1, CONFIG.MULE_MIN_DISTINCT_CASES * 2))
            mule_score = round(
                100 * (CONFIG.MULE_SCORE_VICTIM_WEIGHT * victim_component
                       + CONFIG.MULE_SCORE_CASE_WEIGHT * case_component), 1
            )
            mules.append({
                "entity": nid,
                "entity_type": attrs.get("entity_type"),
                "label": attrs.get("label"),
                "distinct_victims": len(distinct_victims),
                "distinct_cases": len(case_ids),
                "connected_cases": sorted(case_ids),
                "mule_score": mule_score,
                # The mule score already blends victim/case support, so it
                # doubles directly as the confidence in this flag.
                "confidence": mule_score,
            })

    mules.sort(key=lambda m: m["mule_score"], reverse=True)
    logger.info("Money mule detection complete. flagged_entities=%d", len(mules))
    return mules

# ## 10. Module 8 - Central Actor Detection
# 
# Three independent centrality signals are combined because each one
# captures a different notion of "importance" and none is reliable alone:
#   - degree centrality       -> how many distinct entities this node touches
#   - betweenness centrality  -> how often this node sits on the shortest
#                                 path between two other entities, i.e. how
#                                 much of the network's traffic routes
#                                 through it
#   - PageRank                -> how important this node is transitively,
#                                 weighting links from already-important
#                                 neighbors more than links from peripheral ones
# A node that scores highly across all three is a much stronger kingpin
# candidate than one that only scores highly on a single metric.


_ROLE_BY_ENTITY_TYPE: Dict[str, str] = {
    EntityType.PHONE.value: "Primary Caller",
    EntityType.UPI.value: "Money Receiver",
    EntityType.BANK_ACCOUNT.value: "Money Receiver",
    EntityType.WALLET_ID.value: "Money Receiver",
    EntityType.DEVICE_ID.value: "Device Controller",
    EntityType.IMEI.value: "Device Controller",
    EntityType.EMAIL.value: "Communication Channel",
    EntityType.IP.value: "Infrastructure",
    EntityType.URL.value: "Infrastructure",
    EntityType.DOMAIN.value: "Infrastructure",
    EntityType.ORGANIZATION.value: "Financial Institution",
    EntityType.VICTIM.value: "Victim",
}


def _assign_actor_role(entity_type: str, is_top_overall: bool) -> str:
    '''Maps an entity type to a plain-language investigative role. The single
    highest-ranked actor overall additionally carries the "Campaign Leader"
    role, on top of its type-based role, since a kingpin is defined by its
    position in the network rather than by what kind of entity it happens
    to be.'''
    base_role = _ROLE_BY_ENTITY_TYPE.get(entity_type, "Unclassified Actor")
    return f"{base_role} / Campaign Leader" if is_top_overall else base_role


def detect_central_actors(fng: FraudNetworkGraph) -> List[Dict[str, Any]]:
    '''Module 8 entry point.'''
    analytic_graph = fng.undirected_view(exclude_types={EntityType.CASE.value})
    if analytic_graph.number_of_nodes() < 2:
        return []

    degree = nx.degree_centrality(analytic_graph)
    try:
        betweenness = nx.betweenness_centrality(analytic_graph)
    except Exception as exc:
        logger.warning("Betweenness centrality failed, defaulting to zero: %s", exc)
        betweenness = {n: 0.0 for n in analytic_graph.nodes}
    try:
        pagerank = nx.pagerank(analytic_graph)
    except Exception as exc:
        logger.warning("PageRank failed, defaulting to zero: %s", exc)
        pagerank = {n: 0.0 for n in analytic_graph.nodes}

    # PageRank values are typically much smaller than degree/betweenness
    # centrality (they sum to 1 across the whole graph), so they are
    # min-max normalized against the graph's own range before blending,
    # to keep the three signals on a comparable scale.
    pagerank_values = list(pagerank.values())
    pr_min, pr_max = (min(pagerank_values), max(pagerank_values)) if pagerank_values else (0.0, 1.0)
    pr_range = (pr_max - pr_min) or 1.0

    ranked: List[Dict[str, Any]] = []
    for nid, attrs in analytic_graph.nodes(data=True):
        pagerank_norm = (pagerank.get(nid, 0.0) - pr_min) / pr_range
        combined = round(
            CONFIG.CENTRALITY_DEGREE_WEIGHT * degree.get(nid, 0.0)
            + CONFIG.CENTRALITY_BETWEENNESS_WEIGHT * betweenness.get(nid, 0.0)
            + CONFIG.CENTRALITY_PAGERANK_WEIGHT * pagerank_norm, 4
        )
        ranked.append({
            "entity": nid,
            "entity_type": attrs.get("entity_type"),
            "label": attrs.get("label"),
            "degree_centrality": round(degree.get(nid, 0.0), 4),
            "betweenness_centrality": round(betweenness.get(nid, 0.0), 4),
            "pagerank": round(pagerank.get(nid, 0.0), 4),
            "centrality_score": combined,
            "connected_cases": sorted(fng.entity_cases.get(nid, set())),
        })

    ranked.sort(key=lambda r: r["centrality_score"], reverse=True)
    top_k = ranked[:CONFIG.CENTRAL_ACTOR_TOP_K]

    for idx, actor in enumerate(top_k):
        actor["role"] = _assign_actor_role(actor["entity_type"], is_top_overall=(idx == 0))
        # Confidence grows with both the centrality score itself and how
        # many cases corroborate this actor's position in the network - a
        # central node backed by only one case is a weaker claim than one
        # backed by five.
        case_support = min(1.0, len(actor["connected_cases"]) / 5.0)
        actor["confidence"] = round(min(99.0, 100 * (0.7 * actor["centrality_score"] * 2 + 0.3 * case_support)), 1)

    logger.info("Central actor detection complete. top_entity=%s", top_k[0]["entity"] if top_k else None)
    return top_k

# ## 11. Module 9 - Cross-Case Matching


def match_case_against_network(fng: FraudNetworkGraph, case_id: str) -> Dict[str, Any]:
    '''
    Module 9 entry point. For one specific case (typically the case that
    was just ingested), reports which of its entities already existed
    elsewhere in the network and which other case_ids they connect back to.
    '''
    case = fng.cases.get(case_id)
    if case is None:
        raise FraudNetworkIntelligenceError(f"Unknown case_id for cross-case matching: {case_id!r}")

    entities = collect_entities_from_case(case)
    matches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for entity_type, raw_values in entities.items():
        for raw in raw_values:
            nid = node_id(entity_type, raw)
            other_cases = sorted(fng.entity_cases.get(nid, set()) - {case_id})
            if other_cases:
                matches[entity_type].append({"entity": nid, "label": raw, "matched_cases": other_cases})

    all_matched_cases: Set[str] = set()
    for entries in matches.values():
        for entry in entries:
            all_matched_cases.update(entry["matched_cases"])

    return {
        "case_id": case_id,
        "matches_by_entity_type": dict(matches),
        "linked_case_ids": sorted(all_matched_cases),
        "is_linked_to_prior_cases": bool(all_matched_cases),
    }

# ## 12. Module 10 - Fraud Campaign Detection


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def detect_fraud_campaigns(communities: List[Dict[str, Any]], fng: FraudNetworkGraph) -> List[Dict[str, Any]]:
    '''
    Module 10 entry point. Reframes each sufficiently large, fraud-type-
    consistent community as a named "campaign" - the same operation run
    against many victims - rather than a list of unrelated case numbers.
    Adds a rough timeline (first/latest seen, estimated duration), an
    average-amount and growth-trend read on whether the campaign appears
    to be escalating, and an Active/Dormant status based on recency.
    '''
    campaigns: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for idx, community in enumerate(communities, start=1):
        case_ids = community["connected_cases"]
        if len(case_ids) < CONFIG.COMMUNITY_MIN_SIZE:
            continue

        linked_cases = [fng.cases[cid] for cid in case_ids if cid in fng.cases]
        victims = {c.victim_id for c in linked_cases if c.victim_id}
        amounts = [c.amount_involved for c in linked_cases]
        total_amount = sum(amounts)
        average_amount = round(total_amount / len(amounts), 2) if amounts else 0.0

        # Order cases chronologically wherever a timestamp is available;
        # cases without one are simply excluded from the timeline math.
        timestamped = sorted(
            ((c, _parse_timestamp(c.timestamp)) for c in linked_cases if _parse_timestamp(c.timestamp)),
            key=lambda pair: pair[1],
        )
        first_seen = timestamped[0][1].isoformat() if timestamped else None
        latest_seen = timestamped[-1][1].isoformat() if timestamped else None
        duration_days = (timestamped[-1][1] - timestamped[0][1]).days if len(timestamped) >= 2 else 0

        # Growth trend: compare the average amount in the earlier half of
        # the timeline against the later half. This is a coarse proxy (no
        # true velocity data is available) and is reported as a direction,
        # not a precise growth rate.
        growth_trend = "Insufficient data"
        if len(timestamped) >= 4:
            midpoint = len(timestamped) // 2
            earlier_avg = sum(c.amount_involved for c, _ in timestamped[:midpoint]) / midpoint
            later_avg = sum(c.amount_involved for c, _ in timestamped[midpoint:]) / (len(timestamped) - midpoint)
            if later_avg > earlier_avg * 1.1:
                growth_trend = "Escalating"
            elif later_avg < earlier_avg * 0.9:
                growth_trend = "Declining"
            else:
                growth_trend = "Stable"

        status = "Active"
        if latest_seen:
            latest_dt = timestamped[-1][1]
            if (now - latest_dt).days > CONFIG.CAMPAIGN_ACTIVE_WINDOW_DAYS:
                status = "Dormant"

        confidence = community["confidence"]

        campaigns.append({
            "campaign_id": f"CAMPAIGN-{idx:02d}",
            "dominant_fraud": community["dominant_fraud"],
            "linked_cases": case_ids,
            "victim_count": len(victims),
            "total_amount_involved": round(total_amount, 2),
            "average_amount_involved": average_amount,
            "core_entities": community["members"],
            "first_seen": first_seen,
            "latest_seen": latest_seen,
            "estimated_duration_days": duration_days,
            "growth_trend": growth_trend,
            "status": status,
            "confidence": confidence,
        })

    logger.info("Fraud campaign detection complete. campaigns_found=%d", len(campaigns))
    return campaigns

# ## 13. Module 11 - Geographic Spread


def summarize_geographic_spread(communities: List[Dict[str, Any]], fng: FraudNetworkGraph) -> List[Dict[str, Any]]:
    '''
    Module 11 entry point. For each community, aggregates which
    cities/states its linked cases were reported from. Notebook 7 owns
    the actual mapping UI; this module only stores the raw spread so that
    later notebook has something to plot.
    '''
    spread: List[Dict[str, Any]] = []
    for community in communities:
        cities: Set[str] = set()
        states: Set[str] = set()
        for cid in community["connected_cases"]:
            case = fng.cases.get(cid)
            if case:
                if case.city:
                    cities.add(case.city)
                if case.state:
                    states.add(case.state)
        spread.append({
            "community_id": community["community_id"],
            "cities": sorted(cities),
            "states": sorted(states),
            "spans_multiple_states": len(states) > 1,
        })
    return spread


def assess_community_threat(communities: List[Dict[str, Any]], fng: FraudNetworkGraph, geographic_spread: List[Dict[str, Any]]) -> None:
    '''
    Module 11b. Folds victim count, total money involved, and geographic
    spread into a single "threat_assessment" block per community, in the
    style of an investigator-facing dashboard ("37 victims, Rs 2.4 Cr,
    spread across 4 states, Critical"). Mutates the community dicts in
    place since this is purely additive enrichment on top of Module 6's output.
    '''
    spread_by_community = {s["community_id"]: s for s in geographic_spread}
    for community in communities:
        case_ids = community["connected_cases"]
        victims = {
            fng.cases[cid].victim_id for cid in case_ids
            if cid in fng.cases and fng.cases[cid].victim_id
        }
        total_amount = sum(fng.cases[cid].amount_involved for cid in case_ids if cid in fng.cases)
        spread = spread_by_community.get(community["community_id"], {"states": [], "cities": []})

        community["threat_assessment"] = {
            "threat_level": community["priority"],
            "victim_count": len(victims),
            "total_amount_involved": round(total_amount, 2),
            "states_affected": len(spread["states"]),
            "cities_affected": len(spread["cities"]),
        }

# ## 14. Module 12 - Risk Propagation


def propagate_risk(fng: FraudNetworkGraph) -> Dict[str, float]:
    '''
    Module 12 entry point. Seeds every entity node with the average
    Notebook-2 risk score of the cases it appears in, then iteratively
    lets each node's risk absorb a decayed fraction of its neighbors'
    risk for a fixed number of hops. A phone number that on its own looks
    unremarkable but sits directly next to a UPI ID already tied to
    several high-risk cases ends up with an elevated propagated score,
    which is exactly the "17 previous scams raise this case's risk"
    behaviour the design calls for.
    '''
    analytic_graph = fng.undirected_view(exclude_types={EntityType.CASE.value})
    if analytic_graph.number_of_nodes() == 0:
        return {}

    risk: Dict[str, float] = {}
    for nid in analytic_graph.nodes:
        case_ids = fng.entity_cases.get(nid, set())
        scores = [fng.cases[cid].risk_score for cid in case_ids if cid in fng.cases]
        risk[nid] = sum(scores) / len(scores) if scores else 0.0

    for _ in range(CONFIG.RISK_PROPAGATION_ITERATIONS):
        updated = dict(risk)
        for nid in analytic_graph.nodes:
            neighbors = list(analytic_graph.neighbors(nid))
            if not neighbors:
                continue
            neighbor_avg = sum(risk[n] for n in neighbors) / len(neighbors)
            updated[nid] = min(100.0, risk[nid] + CONFIG.RISK_PROPAGATION_DECAY * max(0.0, neighbor_avg - risk[nid]))
        risk = updated

    return {nid: round(score, 1) for nid, score in risk.items()}


def compute_network_adjusted_case_risk(
    case: CaseRecord,
    entities: Dict[str, List[str]],
    propagated_risk: Dict[str, float],
    fng: FraudNetworkGraph,
    mules: List[Dict[str, Any]],
    campaigns: List[Dict[str, Any]],
) -> Dict[str, Any]:
    '''
    Uses the propagated risk map to decide whether a case's own,
    standalone Notebook-2 score should be raised because of the company
    its entities keep. The boost is capped (Config.RISK_PROPAGATION_MAX_BOOST)
    so that network effects can raise suspicion but cannot, by themselves,
    manufacture a maximum-risk case out of a genuinely low-risk one.

    Beyond the number itself, this also builds a plain-language "reasons"
    list explaining WHY the score moved - which shared entity drove it,
    how many other cases that entity already appears in, whether it is
    already flagged as a likely money mule, and whether it belongs to an
    active fraud campaign - since a bare "50 -> 75" is far less useful to
    an investigator than knowing what caused it.
    '''
    max_neighbor_risk = case.risk_score
    driving_entity = None
    driving_entity_type = None
    for entity_type, raw_values in entities.items():
        for raw in raw_values:
            nid = node_id(entity_type, raw)
            neighbor_risk = propagated_risk.get(nid, 0.0)
            if neighbor_risk > max_neighbor_risk:
                max_neighbor_risk = neighbor_risk
                driving_entity = nid
                driving_entity_type = entity_type

    boost = min(CONFIG.RISK_PROPAGATION_MAX_BOOST, max(0.0, max_neighbor_risk - case.risk_score))
    adjusted_risk = round(min(100.0, case.risk_score + boost), 1)

    reasons: List[str] = []
    if driving_entity and boost > 0:
        other_cases = sorted(fng.entity_cases.get(driving_entity, set()) - {case.case_id})
        entity_label = driving_entity.split(":", 1)[-1]
        reasons.append(
            f"Shares {driving_entity_type.replace('_', ' ')} '{entity_label}' with {len(other_cases)} other case(s): "
            f"{', '.join(other_cases) if other_cases else 'none on file'}."
        )

        mule_match = next((m for m in mules if m["entity"] == driving_entity), None)
        if mule_match:
            reasons.append(
                f"This {driving_entity_type.replace('_', ' ')} is already flagged as a likely money mule "
                f"(mule score {mule_match['mule_score']})."
            )

        matching_campaigns = [c for c in campaigns if case.case_id in c["linked_cases"] and len(c["linked_cases"]) > 1]
        if matching_campaigns:
            top_campaign = matching_campaigns[0]
            reasons.append(
                f"Case belongs to {top_campaign['campaign_id']}, an existing '{top_campaign['dominant_fraud']}' "
                f"campaign with {top_campaign['victim_count']} known victim(s), status {top_campaign['status']}."
            )
    else:
        reasons.append("No network signal exceeded this case's own standalone risk score; no adjustment was made.")

    return {
        "original_risk": case.risk_score,
        "network_adjusted_risk": adjusted_risk,
        "boost_applied": round(boost, 1),
        "driving_entity": driving_entity,
        "reasons": reasons,
    }

# ## 15. Module 14 - Graph Visualization


_NODE_COLORS: Dict[str, str] = {
    EntityType.PHONE.value: "#d62728",
    EntityType.UPI.value: "#9467bd",
    EntityType.EMAIL.value: "#1f77b4",
    EntityType.BANK_ACCOUNT.value: "#8c564b",
    EntityType.DEVICE_ID.value: "#ff7f0e",
    EntityType.IMEI.value: "#e377c2",
    EntityType.IP.value: "#7f7f7f",
    EntityType.WALLET_ID.value: "#bcbd22",
    EntityType.URL.value: "#17becf",
    EntityType.DOMAIN.value: "#17becf",
    EntityType.ORGANIZATION.value: "#2ca02c",
    EntityType.VICTIM.value: "#000000",
    EntityType.CASE.value: "#c7c7c7",
}


def build_network_visualization(fng: FraudNetworkGraph, output_path: str, central_actors: List[Dict[str, Any]]) -> Optional[str]:
    '''
    Module 14 entry point. Draws the full graph (entities, victims, and
    case nodes) with a spring layout, coloring nodes by entity type and
    sizing the top central actors larger so they visually pop out. Skips
    silently (returns None) if matplotlib is not installed, since the
    intelligence package must remain usable without a plotting backend.
    '''
    if not _MATPLOTLIB_AVAILABLE:
        logger.info("matplotlib not available; skipping graph visualization.")
        return None

    graph = fng.graph
    if graph.number_of_nodes() == 0:
        return None

    top_actor_ids = {actor["entity"] for actor in central_actors}
    pos = nx.spring_layout(graph, seed=42, k=0.6)

    plt.figure(figsize=(12, 9))
    node_colors = [_NODE_COLORS.get(attrs.get("entity_type"), "#999999") for _, attrs in graph.nodes(data=True)]
    node_sizes = [900 if nid in top_actor_ids else 260 for nid in graph.nodes]

    nx.draw_networkx_nodes(graph, pos, node_color=node_colors, node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_edges(graph, pos, alpha=0.25, arrows=False)
    labels = {nid: attrs.get("label", nid) for nid, attrs in graph.nodes(data=True) if nid in top_actor_ids}
    nx.draw_networkx_labels(graph, pos, labels=labels, font_size=9)

    plt.title("Fraud Network Intelligence Graph")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    logger.info("Network visualization saved to %s", output_path)
    return output_path


# ============================================================================
# 15b. Module 15 - Fraud Flow Reconstruction
# ============================================================================
#
# Notebook 6 up to this point only reports WHAT is connected. This module
# reconstructs HOW the scam actually moved - from the victim, through the
# communication channel, to the payment instrument, to wherever the money
# was ultimately routed - by walking the same explicit relation table
# used in Module 3, restricted to just this one case's entities. It does
# not have access to a real transaction ledger, so the money-movement
# steps are phrased as "suspected" routing rather than a confirmed trace.

_RELATION_PHRASES: Dict[str, str] = {
    "received_call_from": "Victim received a call from",
    "received_email_from": "Victim received an email from",
    "belongs_to": "traced to device",
    "has_imei": "with IMEI",
    "accessed_from": "accessed from IP",
    "used_upi": "Money was sent via UPI to",
    "registered_email": "which is registered to email",
    "linked_wallet": "then routed to wallet",
    "linked_account": "then routed to bank account",
    "held_at": "held at institution",
    "hosted_on": "hosted on domain",
}

# The order in which relation types are followed when walking the chain
# outward from the victim, so the reconstructed flow reads victim-first
# and money-movement-last rather than in an arbitrary edge order.
_FLOW_RELATION_ORDER = [
    "received_call_from", "received_email_from", "belongs_to", "has_imei", "accessed_from",
    "used_upi", "registered_email", "linked_wallet", "linked_account", "held_at", "hosted_on",
]


def reconstruct_fraud_flow(case: CaseRecord, entities: Dict[str, List[str]], fng: FraudNetworkGraph) -> Dict[str, Any]:
    '''
    Module 15 entry point. Builds a human-readable, ordered attack-flow
    narrative for one case (e.g. "Victim received a call from 987... ->
    Money was sent via UPI to rahul@okaxis -> then routed to bank account
    123...") by following the same relation table used to build the graph,
    restricted to entities that actually appear together in this case's
    edges.
    '''
    victim_id = case.victim_id
    if not victim_id:
        return {"steps": [], "flow_diagram": "No victim identifier on file; flow could not be reconstructed."}

    case_node = node_id(EntityType.CASE.value, case.case_id)
    victim_node = node_id(EntityType.VICTIM.value, victim_id)

    # Only consider edges that were actually recorded for this case_id, so
    # a shared UPI id from a different case doesn't leak into this case's flow.
    case_edges = [
        (u, v, attrs) for u, v, attrs in fng.graph.edges(data=True)
        if attrs.get("case_id") == case.case_id and attrs.get("relation") in _RELATION_PHRASES
    ]

    steps: List[Dict[str, str]] = []
    visited: Set[str] = {victim_node}
    frontier = [victim_node]

    for relation in _FLOW_RELATION_ORDER:
        next_frontier: List[str] = []
        for u, v, attrs in case_edges:
            if attrs.get("relation") != relation:
                continue
            source, target = (u, v) if u in visited else (v, u) if v in visited else (None, None)
            if source is None or target in visited:
                continue
            label = target.split(":", 1)[-1]
            steps.append({"relation": relation, "description": f"{_RELATION_PHRASES[relation]} {label}", "entity": target})
            visited.add(target)
            next_frontier.append(target)
        frontier = next_frontier or frontier

    flow_diagram = " -> ".join([f"Victim {victim_id}"] + [s["description"] for s in steps]) if steps else f"Victim {victim_id} (no downstream entities recorded for this case)."

    return {"case_id": case.case_id, "steps": steps, "flow_diagram": flow_diagram}


# ============================================================================
# 15c. Module 16 - Timeline Reconstruction
# ============================================================================


def reconstruct_case_timeline(case: CaseRecord) -> Dict[str, Any]:
    '''
    Module 16 entry point. Orders a case's optional fine-grained event log
    (call, message, payment, bank transfer, wallet transfer, ...) into a
    chronological timeline. Cases logged without an event log (the common
    case for older complaints) simply return an empty timeline rather than
    failing, since this module is an enrichment, not a requirement.
    '''
    if not case.events:
        return {"case_id": case.case_id, "timeline": [], "notes": ["No fine-grained event log was recorded for this case."]}

    parsed_events = [
        (evt.get("event", "Unknown event"), _parse_timestamp(evt.get("timestamp")))
        for evt in case.events
    ]
    parsed_events = [e for e in parsed_events if e[1] is not None]
    parsed_events.sort(key=lambda e: e[1])

    timeline = [{"event": name, "timestamp": ts.isoformat()} for name, ts in parsed_events]
    total_span_minutes = None
    if len(parsed_events) >= 2:
        total_span_minutes = round((parsed_events[-1][1] - parsed_events[0][1]).total_seconds() / 60, 1)

    return {"case_id": case.case_id, "timeline": timeline, "total_span_minutes": total_span_minutes, "notes": []}

# ## 16. Module 13 - Intelligence Summary


def build_intelligence_summary(
    communities: List[Dict[str, Any]],
    campaigns: List[Dict[str, Any]],
    mules: List[Dict[str, Any]],
    central_actors: List[Dict[str, Any]],
    risk_adjustment: Optional[Dict[str, Any]],
) -> List[str]:
    '''Module 13 entry point. Plain-language rollup for an investigator, not just raw JSON.'''
    lines: List[str] = []

    if communities:
        top = communities[0]
        lines.append(
            f"Largest connected ring ({top['community_id']}) links {len(top['connected_cases'])} case(s) "
            f"across {top['size']} shared entities, dominant pattern: {top['dominant_fraud']}."
        )
    else:
        lines.append("No multi-entity communities were found; cases currently appear unconnected.")

    if campaigns:
        lines.append(f"{len(campaigns)} fraud campaign(s) identified from repeated, connected entity patterns.")

    if mules:
        top_mule = mules[0]
        lines.append(
            f"{len(mules)} account(s) show money-mule characteristics; top candidate is "
            f"{top_mule['label']} (mule score {top_mule['mule_score']}, linked to "
            f"{top_mule['distinct_victims']} distinct victims across {top_mule['distinct_cases']} cases)."
        )
    else:
        lines.append("No accounts currently meet the money-mule threshold.")

    if central_actors:
        leader = central_actors[0]
        lines.append(
            f"Central actor in the network is {leader['label']} ({leader['entity_type']}), "
            f"centrality score {leader['centrality_score']}, connected to {len(leader['connected_cases'])} case(s)."
        )

    if risk_adjustment and risk_adjustment["boost_applied"] > 0:
        lines.append(
            f"Network context raised this case's risk score from {risk_adjustment['original_risk']} "
            f"to {risk_adjustment['network_adjusted_risk']}, driven by its link to {risk_adjustment['driving_entity']}."
        )

    return lines


# ============================================================================
# 16b. Module 17 - Police Intelligence Report (PDF)
# ============================================================================
#
# Renders the assembled intelligence package into a single, one-click PDF
# an investigator can hand upward without reading raw JSON: the leader,
# the mule accounts, victim/amount totals, the reconstructed attack flow,
# the timeline, recommendations, and the network graph image. Uses
# `reportlab` when available and degrades to writing a plain-text report
# (same content, no layout) when it is not, since the underlying
# intelligence must remain available even without a PDF backend installed.

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak,
    )
    from reportlab.lib import colors
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False


def _build_report_text_lines(package: Dict[str, Any]) -> List[str]:
    '''Shared content builder: produces the same information regardless of whether it ends up in a PDF or a plain-text fallback.'''
    lines: List[str] = []
    lines.append(f"POLICE INTELLIGENCE REPORT - {package['network_id']}")
    lines.append(f"Focus case: {package['focus_case_id']}")
    lines.append("")
    lines.append("SUMMARY")
    lines.extend(f"  - {line}" for line in package["intelligence_summary"])
    lines.append("")

    if package["central_actor"]:
        leader = package["central_actor"]
        lines.append("SUSPECTED LEADER / CENTRAL ACTOR")
        lines.append(f"  Entity: {leader['label']} ({leader['entity_type']})")
        lines.append(f"  Role: {leader.get('role', 'Unclassified')}")
        lines.append(f"  Centrality score: {leader['centrality_score']}  |  Confidence: {leader.get('confidence')}%")
        lines.append(f"  Connected cases: {', '.join(leader['connected_cases'])}")
        lines.append("")

    if package["money_mule_accounts"]:
        lines.append("MONEY MULE ACCOUNTS")
        for mule in package["money_mule_accounts"]:
            lines.append(
                f"  - {mule['label']} ({mule['entity_type']}): {mule['distinct_victims']} victims, "
                f"{mule['distinct_cases']} cases, mule score {mule['mule_score']}"
            )
        lines.append("")

    if package["communities"]:
        lines.append("FRAUD RINGS / COMMUNITIES")
        for community in package["communities"]:
            threat = community.get("threat_assessment", {})
            lines.append(
                f"  - {community['community_id']}: {community['dominant_fraud']}, priority {community['priority']}, "
                f"{threat.get('victim_count', '?')} victim(s), "
                f"Rs {threat.get('total_amount_involved', 0):,.0f}, "
                f"{threat.get('states_affected', '?')} state(s) affected"
            )
        lines.append("")

    if package["fraud_campaigns"]:
        lines.append("CAMPAIGNS")
        for campaign in package["fraud_campaigns"]:
            lines.append(
                f"  - {campaign['campaign_id']}: {campaign['dominant_fraud']}, status {campaign['status']}, "
                f"trend {campaign['growth_trend']}, first seen {campaign['first_seen']}, latest {campaign['latest_seen']}"
            )
        lines.append("")

    flow = package.get("fraud_flow")
    if flow and flow.get("steps"):
        lines.append("RECONSTRUCTED FRAUD FLOW (focus case)")
        lines.append(f"  {flow['flow_diagram']}")
        lines.append("")

    timeline = package.get("case_timeline")
    if timeline and timeline.get("timeline"):
        lines.append("TIMELINE (focus case)")
        for event in timeline["timeline"]:
            lines.append(f"  {event['timestamp']}  -  {event['event']}")
        lines.append("")

    risk = package["risk_propagation"]
    lines.append("RISK ASSESSMENT")
    lines.append(f"  Standalone risk: {risk['original_risk']}  ->  Network-adjusted risk: {risk['network_adjusted_risk']}")
    for reason in risk["reasons"]:
        lines.append(f"  Reason: {reason}")
    lines.append("")

    lines.append("RECOMMENDATION")
    lines.append(
        "  Escalate to the cyber-crime cell with priority matching the highest-priority community above; "
        "freeze flagged mule accounts pending verification; cross-reference the central actor against "
        "existing watchlists."
    )
    return lines


def generate_police_intelligence_report(package: Dict[str, Any], output_path: str) -> str:
    '''
    Module 17 entry point. Writes a formatted PDF report when reportlab is
    available; otherwise writes a plain-text report with the same content
    to the same path (extension swapped to .txt) so the report is never
    silently lost. Returns the path actually written.
    '''
    lines = _build_report_text_lines(package)

    if not _REPORTLAB_AVAILABLE:
        fallback_path = os.path.splitext(output_path)[0] + ".txt"
        with open(fallback_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        logger.info("reportlab not available; wrote plain-text report to %s", fallback_path)
        return fallback_path

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=16)
    heading_style = ParagraphStyle("ReportHeading", parent=styles["Heading2"], spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("ReportBody", parent=styles["BodyText"], spaceAfter=2)

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story: List[Any] = []

    story.append(Paragraph(f"Police Intelligence Report - {package['network_id']}", title_style))
    story.append(Paragraph(f"Focus case: {package['focus_case_id']}", body_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Summary", heading_style))
    for line in package["intelligence_summary"]:
        story.append(Paragraph(line, body_style))

    if package["central_actor"]:
        leader = package["central_actor"]
        story.append(Paragraph("Suspected Leader / Central Actor", heading_style))
        leader_table = Table([
            ["Entity", leader["label"]],
            ["Type", leader["entity_type"]],
            ["Role", leader.get("role", "Unclassified")],
            ["Centrality score", str(leader["centrality_score"])],
            ["Confidence", f"{leader.get('confidence')}%"],
            ["Connected cases", ", ".join(leader["connected_cases"])],
        ], colWidths=[4 * cm, 11 * cm])
        leader_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(leader_table)

    if package["money_mule_accounts"]:
        story.append(Paragraph("Money Mule Accounts", heading_style))
        mule_rows = [["Entity", "Type", "Victims", "Cases", "Mule Score"]]
        for mule in package["money_mule_accounts"]:
            mule_rows.append([mule["label"], mule["entity_type"], str(mule["distinct_victims"]), str(mule["distinct_cases"]), str(mule["mule_score"])])
        mule_table = Table(mule_rows, colWidths=[5 * cm, 3 * cm, 2.3 * cm, 2.3 * cm, 2.4 * cm])
        mule_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(mule_table)

    if package["communities"]:
        story.append(Paragraph("Fraud Rings / Communities", heading_style))
        comm_rows = [["Community", "Fraud Type", "Priority", "Victims", "Amount (Rs)", "States"]]
        for community in package["communities"]:
            threat = community.get("threat_assessment", {})
            comm_rows.append([
                community["community_id"], community["dominant_fraud"], community["priority"],
                str(threat.get("victim_count", "?")), f"{threat.get('total_amount_involved', 0):,.0f}",
                str(threat.get("states_affected", "?")),
            ])
        comm_table = Table(comm_rows, colWidths=[2.6 * cm, 3.6 * cm, 2.2 * cm, 2 * cm, 3 * cm, 1.8 * cm])
        comm_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]))
        story.append(comm_table)

    flow = package.get("fraud_flow")
    if flow and flow.get("steps"):
        story.append(Paragraph("Reconstructed Fraud Flow (focus case)", heading_style))
        story.append(Paragraph(flow["flow_diagram"], body_style))

    timeline = package.get("case_timeline")
    if timeline and timeline.get("timeline"):
        story.append(Paragraph("Timeline (focus case)", heading_style))
        for event in timeline["timeline"]:
            story.append(Paragraph(f"{event['timestamp']} - {event['event']}", body_style))

    risk = package["risk_propagation"]
    story.append(Paragraph("Risk Assessment", heading_style))
    story.append(Paragraph(f"Standalone risk: {risk['original_risk']} -&gt; Network-adjusted risk: {risk['network_adjusted_risk']}", body_style))
    for reason in risk["reasons"]:
        story.append(Paragraph(f"Reason: {reason}", body_style))

    if package.get("graph_visualization") and os.path.exists(package["graph_visualization"]):
        story.append(PageBreak())
        story.append(Paragraph("Network Graph", heading_style))
        story.append(RLImage(package["graph_visualization"], width=16 * cm, height=12 * cm))

    story.append(Paragraph("Recommendation", heading_style))
    story.append(Paragraph(
        "Escalate to the cyber-crime cell with priority matching the highest-priority community above; "
        "freeze flagged mule accounts pending verification; cross-reference the central actor against "
        "existing watchlists.", body_style,
    ))

    doc.build(story)
    logger.info("Police intelligence report saved to %s", output_path)
    return output_path

# ## 17. Module 15 - Intelligence Package (Orchestration)


def build_audit_log(fng: FraudNetworkGraph, focus_case_id: Optional[str]) -> Dict[str, Any]:
    '''Hashes the sorted set of case ids currently in the graph for tamper-evident audit purposes.'''
    case_ids_sorted = sorted(fng.cases.keys())
    digest_input = json.dumps(case_ids_sorted, sort_keys=True).encode("utf-8")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_set_hash": hashlib.sha256(digest_input).hexdigest(),
        "total_cases_in_network": len(case_ids_sorted),
        "focus_case_id": focus_case_id,
        "notebook_version": CONFIG.NOTEBOOK_VERSION,
    }


def analyze_fraud_network(
    cases: List[CaseRecord],
    focus_case_id: Optional[str] = None,
    save_visualization: bool = True,
    generate_report: bool = True,
    visualization_dir: str = "/tmp/notebook6_graphs",
    report_dir: str = "/tmp/notebook6_reports",
) -> Dict[str, Any]:
    '''
    Notebook 6 orchestration - Modules 1-17 combined.

    Ingests every given CaseRecord into a shared FraudNetworkGraph, then
    runs entity normalization, community detection (with threat
    scoring), money-mule detection, central-actor ranking (degree +
    betweenness + PageRank, with an investigative role assigned), cross-
    case matching for the focus case (the case that should be treated as
    "just arrived", defaulting to the last case in the list), fraud-
    campaign detection (with timeline/growth/status), geographic-spread
    aggregation, risk propagation with a plain-language explanation,
    fraud-flow reconstruction, timeline reconstruction, visualization,
    and a one-click PDF police intelligence report - then assembles the
    restructured Fraud Network Intelligence Package that Notebook 3
    consumes when deciding the final action on the focus case.
    '''
    stages: List[Dict[str, str]] = []

    try:
        if not cases:
            raise FraudNetworkIntelligenceError("No case records were provided to analyze_fraud_network().")

        fng = FraudNetworkGraph()
        focus_entities: Dict[str, List[str]] = {}
        for case in cases:
            entities = ingest_case_into_graph(fng, case)
            if case.case_id == (focus_case_id or cases[-1].case_id):
                focus_entities = entities
        stages.append({"stage": "Ingestion", "summary": f"{len(cases)} case(s) ingested; graph has {fng.node_count()} nodes / {fng.edge_count()} edges"})

        focus_case_id = focus_case_id or cases[-1].case_id
        if focus_case_id not in fng.cases:
            raise FraudNetworkIntelligenceError(f"focus_case_id {focus_case_id!r} was not among the provided cases.")

        communities = detect_communities(fng)
        stages.append({"stage": "Community Detection", "summary": f"{len(communities)} community(ies) found"})

        mules = detect_money_mules(fng)
        stages.append({"stage": "Money Mule Detection", "summary": f"{len(mules)} account(s) flagged"})

        central_actors = detect_central_actors(fng)
        stages.append({"stage": "Central Actor Detection", "summary": central_actors[0]["entity"] if central_actors else "none identified"})

        cross_case_matches = match_case_against_network(fng, focus_case_id)
        stages.append({
            "stage": "Cross-Case Matching",
            "summary": f"linked to {len(cross_case_matches['linked_case_ids'])} prior case(s)" if cross_case_matches["is_linked_to_prior_cases"] else "no prior links found",
        })

        campaigns = detect_fraud_campaigns(communities, fng)
        stages.append({"stage": "Campaign Detection", "summary": f"{len(campaigns)} campaign(s) identified"})

        geographic_spread = summarize_geographic_spread(communities, fng)
        assess_community_threat(communities, fng, geographic_spread)
        stages.append({"stage": "Geographic Spread", "summary": f"spread + threat assessed for {len(geographic_spread)} community(ies)"})

        propagated_risk = propagate_risk(fng)
        risk_adjustment = compute_network_adjusted_case_risk(
            fng.cases[focus_case_id], focus_entities, propagated_risk, fng, mules, campaigns
        )
        stages.append({
            "stage": "Risk Propagation",
            "summary": f"{risk_adjustment['original_risk']} -> {risk_adjustment['network_adjusted_risk']} (+{risk_adjustment['boost_applied']})",
        })

        fraud_flow = reconstruct_fraud_flow(fng.cases[focus_case_id], focus_entities, fng)
        stages.append({"stage": "Fraud Flow Reconstruction", "summary": f"{len(fraud_flow['steps'])} step(s) reconstructed"})

        case_timeline = reconstruct_case_timeline(fng.cases[focus_case_id])
        stages.append({"stage": "Timeline Reconstruction", "summary": f"{len(case_timeline['timeline'])} event(s) ordered"})

        visualization_path = None
        if save_visualization:
            os.makedirs(visualization_dir, exist_ok=True)
            suffix = uuid.uuid4().hex[:8]
            visualization_path = build_network_visualization(
                fng, os.path.join(visualization_dir, f"fraud_network_graph_{suffix}.png"), central_actors
            )
        stages.append({"stage": "Visualization", "summary": visualization_path or "skipped (matplotlib unavailable)"})

        summary_lines = build_intelligence_summary(communities, campaigns, mules, central_actors, risk_adjustment)
        audit_log = build_audit_log(fng, focus_case_id)

        # High-risk entity roll-up for the top-level package, grouped by type.
        high_risk_entities: Dict[str, List[str]] = defaultdict(list)
        for actor in central_actors:
            high_risk_entities[actor["entity_type"] + "s"].append(actor["label"])
        for mule in mules:
            key = mule["entity_type"] + "s"
            if mule["label"] not in high_risk_entities[key]:
                high_risk_entities[key].append(mule["label"])

        package: Dict[str, Any] = {
            "network_id": f"NET-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}",
            "focus_case_id": focus_case_id,
            "connected_cases": cross_case_matches["linked_case_ids"],
            "cross_case_matches": cross_case_matches["matches_by_entity_type"],
            "high_risk_entities": dict(high_risk_entities),
            "communities": communities,
            "fraud_campaigns": campaigns,
            "money_mule_accounts": mules,
            "central_actor": central_actors[0] if central_actors else None,
            "central_actors_top_k": central_actors,
            "geographic_spread": geographic_spread,
            "risk_propagation": risk_adjustment,
            "fraud_flow": fraud_flow,
            "case_timeline": case_timeline,
            "intelligence_summary": summary_lines,
            "graph_visualization": visualization_path,
            "graph_stats": {"total_nodes": fng.node_count(), "total_edges": fng.edge_count(), "total_cases": len(fng.cases)},
            "pipeline_stages": stages,
            "audit": audit_log,
            "next_engine": "Decision Intelligence Engine",
        }

        report_path = None
        if generate_report:
            os.makedirs(report_dir, exist_ok=True)
            suffix = uuid.uuid4().hex[:8]
            report_path = generate_police_intelligence_report(
                package, os.path.join(report_dir, f"police_intelligence_report_{suffix}.pdf")
            )
        package["police_intelligence_report"] = report_path
        stages.append({"stage": "Police Report Generation", "summary": report_path or "skipped"})
        package["pipeline_stages"] = stages

        logger.info(
            "Fraud network analysis complete. focus_case=%s connected_cases=%d communities=%d mules=%d",
            focus_case_id, len(package["connected_cases"]), len(communities), len(mules),
        )
        return package

    except FraudNetworkIntelligenceError:
        raise
    except Exception as exc:
        logger.exception("Notebook 6 pipeline failed.")
        raise FraudNetworkIntelligenceError(f"Notebook 6 pipeline failed: {exc}") from exc

# ## 18. Synthetic Case Generation and Deterministic Test Suite
# 
# Real cross-case fraud data is not bundled with this notebook. To
# demonstrate and test the full pipeline deterministically, this section
# synthesizes a set of cases that model one coordinated "Digital Arrest"
# ring (many victims funnelled through a small, shared set of phones/UPI
# IDs/devices) plus a handful of genuinely unrelated, isolated cases. This
# is a pipeline test fixture, not a claim about any real investigation.


def _build_synthetic_cases() -> List[CaseRecord]:
    cases: List[CaseRecord] = []

    # --- The ring: 6 victims funnelled through 2 shared phones, 1 shared
    # UPI id, and 1 shared device, plus a mule account that also appears
    # in a separate, otherwise-unrelated case. ---
    ring_phones = ["9876543210", "9876543211"]
    ring_upi = "rahul@okaxis"
    ring_device = "DEVICE-A1"
    mule_account = "1234567890123456"

    # Cases 1-5 were already investigated and independently scored high by
    # Notebook 2. Case 6 is the new arrival: its own evidence only earns a
    # moderate standalone score, and it is the case used to demonstrate
    # that the network context (Module 12) should lift, not just confirm,
    # a case's risk - mirroring the "85 -> 98" example in the design notes.
    standalone_risk_scores = {1: 88.0, 2: 91.0, 3: 89.0, 4: 93.0, 5: 90.0, 6: 50.0}

    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)

    for i in range(1, 7):
        case_time = base_time.replace(day=min(28, base_time.day + i))
        events = []
        if i == 6:
            # Fine-grained event log for the focus case, to demonstrate
            # Module 16 (Timeline Reconstruction). Deliberately listed out
            # of chronological order to confirm the module actually sorts them.
            events = [
                {"event": "UPI payment made", "timestamp": "2026-07-06T10:12:00+00:00"},
                {"event": "Call received from scammer", "timestamp": "2026-07-06T10:02:00+00:00"},
                {"event": "Funds transferred out of mule account", "timestamp": "2026-07-06T10:35:00+00:00"},
                {"event": "WhatsApp message with fake arrest warrant", "timestamp": "2026-07-06T10:05:00+00:00"},
                {"event": "Wallet transfer flagged", "timestamp": "2026-07-06T10:20:00+00:00"},
            ]

        cases.append(CaseRecord(
            case_id=f"CASE-{i:03d}",
            victim_id=f"VICTIM-{i:03d}",
            fraud_type="Digital Arrest",
            risk_score=standalone_risk_scores[i],
            phone_numbers=[ring_phones[i % 2]],
            upi_ids=[ring_upi],
            device_ids=[ring_device],
            bank_accounts=[mule_account] if i <= 4 else [],
            emails=[f"scammer{i}@fakemail.com"] if i == 1 else [],
            amount_involved=45000.0 + i * 1000,
            city="Pune" if i % 2 == 0 else "Kolhapur",
            state="Maharashtra",
            timestamp=case_time.isoformat(),
            events=events,
        ))

    # A prior, already-closed case that shares only the mule account with
    # the ring above but is otherwise unrelated - this is what should
    # surface a mule detection and a cross-case match, not a full merge.
    cases.append(CaseRecord(
        case_id="CASE-100",
        victim_id="VICTIM-100",
        fraud_type="UPI Fraud",
        risk_score=55.0,
        upi_ids=["different@okhdfcbank"],
        bank_accounts=[mule_account],
        amount_involved=30000.0,
        city="Nagpur",
        state="Maharashtra",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))

    # Two genuinely isolated cases sharing nothing with anyone else.
    cases.append(CaseRecord(
        case_id="CASE-200",
        victim_id="VICTIM-200",
        fraud_type="Romance Scam",
        risk_score=40.0,
        phone_numbers=["9000000001"],
        emails=["loveinterest200@fakemail.com"],
        amount_involved=12000.0,
        city="Mumbai",
        state="Maharashtra",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))
    cases.append(CaseRecord(
        case_id="CASE-201",
        victim_id="VICTIM-201",
        fraud_type="Job Scam",
        risk_score=35.0,
        phone_numbers=["9000000002"],
        upi_ids=["jobfraud@okicici"],
        amount_involved=8000.0,
        city="Nashik",
        state="Maharashtra",
        timestamp=datetime.now(timezone.utc).isoformat(),
    ))

    return cases


def run_notebook6_test_suite() -> Dict[str, Any]:
    print("=== Notebook 6 Test Suite: synthetic fraud network ===\n")

    cases = _build_synthetic_cases()
    checks: List[bool] = []

    def _check(label: str, actual: Any, expected: Any) -> None:
        ok = actual == expected
        checks.append(ok)
        print(f"    [{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")

    def _check_true(label: str, condition: bool) -> None:
        checks.append(condition)
        print(f"    [{'PASS' if condition else 'FAIL'}] {label}")

    print("--- Analyzing full network, focus case = CASE-006 (last ring member) ---")
    package = analyze_fraud_network(cases, focus_case_id="CASE-006")

    # --- Community / ring detection ---
    _check_true("at least one community was detected", len(package["communities"]) > 0)
    if package["communities"]:
        top_community = package["communities"][0]
        _check_true("top community links all 6 ring cases",
                    set(f"CASE-{i:03d}" for i in range(1, 7)).issubset(set(top_community["connected_cases"])))
        _check("top community dominant fraud type is Digital Arrest", top_community["dominant_fraud"], "Digital Arrest")

    # --- Cross-case matching ---
    _check_true("CASE-006 is reported as linked to prior cases",
                len(package["connected_cases"]) > 0)
    _check_true("CASE-006 links back to at least one earlier ring case",
                any(cid in package["connected_cases"] for cid in ["CASE-001", "CASE-002", "CASE-003", "CASE-004", "CASE-005"]))

    # --- Money mule detection ---
    _check_true("at least one money-mule account was flagged", len(package["money_mule_accounts"]) > 0)
    if package["money_mule_accounts"]:
        top_mule = package["money_mule_accounts"][0]
        _check_true("flagged mule account is a financial entity type",
                    top_mule["entity_type"] in ("upi", "bank_account", "wallet_id"))
        _check_true("flagged mule links to at least 3 distinct victims", top_mule["distinct_victims"] >= 3)

    # --- Central actor detection ---
    _check_true("at least one central actor was identified", package["central_actor"] is not None)
    if package["central_actor"]:
        _check_true("central actor is connected to more than one case",
                    len(package["central_actor"]["connected_cases"]) > 1)

    # --- Fraud campaign detection ---
    _check_true("at least one fraud campaign was identified", len(package["fraud_campaigns"]) > 0)

    # --- Geographic spread ---
    _check_true("geographic spread was computed for at least one community", len(package["geographic_spread"]) > 0)

    # --- Risk propagation ---
    risk = package["risk_propagation"]
    _check_true("network-adjusted risk is >= the case's original standalone risk",
                risk["network_adjusted_risk"] >= risk["original_risk"])
    _check_true("risk boost never exceeds the configured cap",
                risk["boost_applied"] <= CONFIG.RISK_PROPAGATION_MAX_BOOST + 0.01)

    # --- Isolated cases should NOT be pulled into the ring's community ---
    isolated_case_ids = {"CASE-200", "CASE-201"}
    ring_community_cases = set(package["communities"][0]["connected_cases"]) if package["communities"] else set()
    _check_true("isolated cases are not merged into the ring's community",
                isolated_case_ids.isdisjoint(ring_community_cases))

    # --- Package structure ---
    expected_keys = {
        "network_id", "focus_case_id", "connected_cases", "cross_case_matches", "high_risk_entities",
        "communities", "fraud_campaigns", "money_mule_accounts", "central_actor", "central_actors_top_k",
        "geographic_spread", "risk_propagation", "fraud_flow", "case_timeline", "intelligence_summary",
        "graph_visualization", "graph_stats", "pipeline_stages", "audit", "next_engine",
        "police_intelligence_report",
    }
    _check_true("package contains all expected top-level keys", expected_keys.issubset(set(package.keys())))
    _check("pipeline has 12 stages", len(package["pipeline_stages"]), 12)

    # --- Risk propagation should clearly demonstrate a boost for the
    # low-standalone-score case sitting next to high-risk network neighbors ---
    _check_true("focus case's network-adjusted risk is meaningfully higher than its standalone score",
                risk["network_adjusted_risk"] > risk["original_risk"] + 5)
    _check_true("risk propagation includes a plain-language explanation", len(risk["reasons"]) > 0)
    _check_true("risk explanation references the shared entity that drove the boost",
                any("shares" in r.lower() for r in risk["reasons"]))

    # --- Improvement 1: central actor carries pagerank, blended score, role, confidence ---
    top_actor = package["central_actor"]
    _check_true("central actor carries a pagerank score", "pagerank" in top_actor)
    _check_true("central actor carries an investigative role", "role" in top_actor and bool(top_actor["role"]))
    _check_true("top central actor is labeled Campaign Leader", "Campaign Leader" in top_actor["role"])
    _check_true("central actor carries a confidence percentage", 0.0 <= top_actor["confidence"] <= 100.0)

    # --- Improvement 2: campaigns carry timeline / growth / status / confidence ---
    top_campaign = package["fraud_campaigns"][0]
    for key in ("first_seen", "latest_seen", "estimated_duration_days", "average_amount_involved", "growth_trend", "status", "confidence"):
        _check_true(f"campaign carries '{key}'", key in top_campaign)
    _check_true("campaign status is Active or Dormant", top_campaign["status"] in ("Active", "Dormant"))

    # --- Improvement 3 / 6: community carries risk, priority, confidence, threat assessment ---
    top_community = package["communities"][0]
    for key in ("community_risk", "priority", "confidence", "threat_assessment"):
        _check_true(f"community carries '{key}'", key in top_community)
    _check_true("community priority is one of the defined levels", top_community["priority"] in ("Critical", "High", "Medium", "Low"))
    _check_true("community threat_assessment carries victim_count and total_amount_involved",
                "victim_count" in top_community["threat_assessment"] and "total_amount_involved" in top_community["threat_assessment"])

    # --- Improvement 5: money mule carries confidence ---
    _check_true("money mule entries carry a confidence field", all("confidence" in m for m in package["money_mule_accounts"]))

    # --- Biggest improvement: fraud flow reconstruction ---
    flow = package["fraud_flow"]
    _check_true("fraud flow reconstruction produced at least one step", len(flow["steps"]) > 0)
    _check_true("fraud flow diagram starts from the victim", flow["flow_diagram"].startswith("Victim"))
    _check_true("fraud flow references the shared UPI id", any("rahul@okaxis" in s["description"] for s in flow["steps"]))

    # --- Timeline reconstruction ---
    timeline = package["case_timeline"]
    _check("timeline has 5 ordered events for the focus case", len(timeline["timeline"]), 5)
    _check("timeline's first event is the call (chronological, not input order)",
           timeline["timeline"][0]["event"], "Call received from scammer")
    _check_true("timeline total span is computed", timeline["total_span_minutes"] is not None)

    # --- Police intelligence report ---
    _check_true("police intelligence report file was generated", package["police_intelligence_report"] is not None)
    _check_true("police intelligence report file exists on disk", os.path.exists(package["police_intelligence_report"]))

    # --- Duplicate entity resolution sanity check: two differently-cased
    # phone formats for the same underlying number should collapse. ---
    dup_case_a = CaseRecord(case_id="CASE-300", victim_id="VICTIM-300", risk_score=50.0, phone_numbers=["+91 98765 43210"])
    dup_case_b = CaseRecord(case_id="CASE-301", victim_id="VICTIM-301", risk_score=50.0, phone_numbers=["09876543210"])
    dup_fng = FraudNetworkGraph()
    ingest_case_into_graph(dup_fng, dup_case_a)
    ingest_case_into_graph(dup_fng, dup_case_b)
    phone_node = node_id(EntityType.PHONE.value, "+91 98765 43210")
    _check("differently formatted phone numbers resolve to the same node id",
           phone_node, node_id(EntityType.PHONE.value, "09876543210"))
    _check("duplicate-resolved phone node links to both cases",
           dup_fng.entity_cases[phone_node], {"CASE-300", "CASE-301"})

    print(f"\nSUMMARY: {sum(checks)}/{len(checks)} checks passed\n")

    print("Intelligence summary (focus case CASE-006):")
    for line in package["intelligence_summary"]:
        print(f"  - {line}")

    print("\nPipeline stages:")
    for s in package["pipeline_stages"]:
        print(f"  {s['stage']:22s} | {s['summary']}")

    print("\nTop central actors:")
    for actor in package["central_actors_top_k"]:
        print(f"  {actor['label']:20s} ({actor['entity_type']:12s}) score={actor['centrality_score']} cases={len(actor['connected_cases'])}")

    print("\nMoney mule accounts flagged:")
    for mule in package["money_mule_accounts"]:
        print(f"  {mule['label']:20s} victims={mule['distinct_victims']} cases={mule['distinct_cases']} mule_score={mule['mule_score']}")

    print("\nFraud campaigns:")
    print(json.dumps(package["fraud_campaigns"], indent=2))

    print(f"\nGraph stats: {package['graph_stats']}")
    print(f"Visualization file: {package['graph_visualization']}")
    print(f"\nAudit log: {json.dumps(package['audit'], indent=2)}")

    return package


if __name__ == "__main__":
    run_notebook6_test_suite()