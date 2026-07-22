# Generated from: geospatial_crime_pattern_intelligence_engine.ipynb
# Converted at: 2026-07-15T01:46:08.761Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # Geospatial Crime Pattern Intelligence Engine
# 
# **ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)**
# 
# **Notebook 7 - Geospatial Crime Pattern Intelligence Engine (Revision 1)**
# 
# ---
# 
# **Mission:** Convert fraud cases into actionable geographic intelligence for police command centers and government agencies - where fraud is concentrated, where it is spreading, which district needs attention next, and which resources should be deployed where.
# 
# **What this notebook is NOT:**
# - It is not a citizen-facing map. It does not just drop pins.
# - It does not classify fraud or score risk. That is Notebook 2's job.
# - It does not decide the final action on a case. That is Notebook 3's job.
# - It does not resolve who is behind the fraud. That is Notebook 6's job.
# 
# **Position in the pipeline:**
# 
# ```
# Citizen report / evidence
#         |
#         v
# Notebook 4 - Digital Evidence Intelligence   (victim address, GPS, timestamp)
#         |
#         v
# Notebook 2 - Fraud Intelligence Engine       (fraud type, standalone risk)
#         |
#         v
# Notebook 6 - Fraud Network Intelligence      (communities, campaigns, mules)
#         |
#         v
# Notebook 7 - Geospatial Intelligence Engine  <- this notebook
#   (turns the above into hotspots, district risk, spread direction,
#    predicted hotspots, and resource recommendations)
#         |
#         v
# Notebook 3 - Decision Intelligence Engine    (final action, using geography
#    as one more signal alongside the network-adjusted risk score)
# ```
# 
# **Design approach:** This notebook does not rely on any external geocoding API or mapping service, since a hackathon judging environment may not have network access. Instead it ships a small offline gazetteer of known city coordinates and a lightweight, dependency-free haversine-distance clustering routine (a hand-rolled DBSCAN) for hotspot detection. This keeps the entire pipeline runnable offline while remaining a faithful, explainable stand-in for a production geocoder / GIS clustering engine. Visualization uses `matplotlib` when available and degrades gracefully (skips image export, keeps all other analysis) when it is not, exactly like Notebook 6.


# ## Imports and Setup


# geospatial_crime_pattern_intelligence_engine.py
# ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)
# Notebook 7 - Geospatial Crime Pattern Intelligence Engine (Revision 1)
#
# Mission (one sentence):
# Convert fraud cases into actionable geographic intelligence for police
# command centers and government agencies - where fraud is concentrated,
# where it is spreading, which district needs attention next, and which
# resources should be deployed where.
#
# What this notebook is NOT:
#   - It is not a citizen-facing map. It does not just drop pins.
#   - It does not classify fraud or score risk. That is Notebook 2's job.
#   - It does not decide the final action on a case. That is Notebook 3's job.
#   - It does not resolve who is behind the fraud. That is Notebook 6's job.
#
# Position in the pipeline:
#
#   Citizen report / evidence
#           |
#           v
#   Notebook 4 - Digital Evidence Intelligence   (victim address, GPS, timestamp)
#           |
#           v
#   Notebook 2 - Fraud Intelligence Engine       (fraud type, standalone risk)
#           |
#           v
#   Notebook 6 - Fraud Network Intelligence      (communities, campaigns, mules)
#           |
#           v
#   Notebook 7 - Geospatial Intelligence Engine  <- this file
#     (turns the above into hotspots, district risk, spread direction,
#      predicted hotspots, and resource recommendations)
#           |
#           v
#   Notebook 3 - Decision Intelligence Engine    (final action, using geography
#      as one more signal alongside the network-adjusted risk score)
#
# Design approach:
# This notebook does not rely on any external geocoding API or mapping
# service, since a hackathon judging environment may not have network
# access. Instead it ships a small offline gazetteer of known city
# coordinates and a lightweight, dependency-free haversine-distance
# clustering routine (a hand-rolled DBSCAN) for hotspot detection. This
# keeps the entire pipeline runnable offline while remaining a faithful,
# explainable stand-in for a production geocoder / GIS clustering engine.
# Visualization uses `matplotlib` when available and degrades gracefully
# (skips image export, keeps all other analysis) when it is not, exactly
# like Notebook 6.

import hashlib
import json
import logging
import math
import os
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")  # headless rendering, no display server required
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:
    _MATPLOTLIB_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("geospatial_crime_pattern_intelligence_engine")

# ## 1. Configuration


class Config:
    '''Central configuration for Notebook 7.'''

    NOTEBOOK_VERSION = "v1.0"

    # --- Module 4: Hotspot detection (haversine DBSCAN) ---
    HOTSPOT_EPS_KM = 5.0             # points within this radius can join the same hotspot
    HOTSPOT_MIN_CASES = 3            # a cluster needs at least this many cases to count as a hotspot
    HOTSPOT_CRITICAL_MIN_CASES = 6
    HOTSPOT_HIGH_MIN_CASES = 4

    # --- Module 6: Time intelligence buckets ---
    TIME_BUCKETS = [
        (0, 6, "Late Night"),
        (6, 12, "Morning"),
        (12, 17, "Afternoon"),
        (17, 21, "Evening"),
        (21, 24, "Night"),
    ]

    # --- Module 7: Spread intelligence ---
    SPREAD_MIN_CITIES = 2            # a campaign needs to touch at least this many distinct cities to show "spread"

    # --- Module 8: District risk ranking (composite score 0-100) ---
    DISTRICT_RISK_CASE_WEIGHT = 0.35
    DISTRICT_RISK_AMOUNT_WEIGHT = 0.25
    DISTRICT_RISK_GROWTH_WEIGHT = 0.20
    DISTRICT_RISK_SEVERITY_WEIGHT = 0.20  # avg standalone/network risk score of cases in the district

    DISTRICT_PRIORITY_CRITICAL_MIN = 80.0
    DISTRICT_PRIORITY_HIGH_MIN = 60.0
    DISTRICT_PRIORITY_MEDIUM_MIN = 35.0

    # --- Module 12: Predictive hotspots ---
    PREDICTION_GROWTH_THRESHOLD = 0.30   # >=30% case growth in the recent window flags a district as "rising"

    # --- Module 10: Nearest cyber cell lookup ---
    MAX_CYBER_CELL_SEARCH_KM = 500.0     # sanity cap; directory is small so this rarely binds

    # --- Overall package confidence, floor/ceiling ---
    MIN_PACKAGE_CONFIDENCE = 40.0
    MAX_PACKAGE_CONFIDENCE = 97.0


CONFIG = Config()
assert abs(
    CONFIG.DISTRICT_RISK_CASE_WEIGHT + CONFIG.DISTRICT_RISK_AMOUNT_WEIGHT
    + CONFIG.DISTRICT_RISK_GROWTH_WEIGHT + CONFIG.DISTRICT_RISK_SEVERITY_WEIGHT - 1.0
) < 1e-6, "District risk composite weights must sum to 1.0."
logger.info("Notebook 7 configuration loaded. version=%s", CONFIG.NOTEBOOK_VERSION)

# ## 2. Exceptions


class GeospatialIntelligenceError(Exception):
    '''Raised when Notebook 7 cannot produce a valid geospatial intelligence package.'''

# ## 3. Offline Gazetteer - Module 2 support data (Geocoder) and Module 3


#
# A small, offline city -> (lat, lon) lookup table. This stands in for a
# real geocoding service. Coordinates are approximate city-centre values,
# adequate for district-level intelligence, not for pinpoint navigation.
# Extend this table with more cities/PIN codes for a production deployment.

CITY_COORDINATES: Dict[str, Tuple[float, float]] = {
    "kolhapur": (16.7050, 74.2433),
    "pune": (18.5204, 73.8567),
    "mumbai": (19.0760, 72.8777),
    "nashik": (19.9975, 73.7898),
    "nagpur": (21.1458, 79.0882),
    "solapur": (17.6599, 75.9064),
    "satara": (17.6805, 74.0183),
    "sangli": (16.8524, 74.5815),
    "aurangabad": (19.8762, 75.3433),
    "thane": (19.2183, 72.9781),
    "delhi": (28.7041, 77.1025),
    "noida": (28.5355, 77.3910),
    "gurgaon": (28.4595, 77.0266),
    "gurugram": (28.4595, 77.0266),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
    "hyderabad": (17.3850, 78.4867),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "ahmedabad": (23.0225, 72.5714),
    "jaipur": (26.9124, 75.7873),
    "lucknow": (26.8467, 80.9462),
    "bhopal": (23.2599, 77.4126),
    "indore": (22.7196, 75.8577),
}

# City -> district mapping. Falls back to using the city itself as the
# "district" if not present here, since not every city needs a distinct
# district entry for a hackathon-scale demo.
CITY_TO_DISTRICT: Dict[str, str] = {
    "mumbai": "Mumbai City",
    "thane": "Thane",
    "pune": "Pune",
    "kolhapur": "Kolhapur",
    "nashik": "Nashik",
    "nagpur": "Nagpur",
    "solapur": "Solapur",
    "satara": "Satara",
    "sangli": "Sangli",
    "aurangabad": "Chhatrapati Sambhajinagar",
    "noida": "Gautam Buddha Nagar",
    "gurgaon": "Gurugram",
    "gurugram": "Gurugram",
}

# Common alternate names / historical names / misspellings, all resolving
# to the same canonical, lowercase gazetteer key. Same idea as Notebook
# 6's Duplicate Entity Resolver, applied to place names instead of
# fraud entities.
CITY_ALIASES: Dict[str, str] = {
    "bombay": "mumbai",
    "poona": "pune",
    "banaras": "lucknow",  # placeholder-safe: unresolved aliases simply fall through unchanged
    "bengaluru": "bengaluru",
    "bangalore": "bengaluru",
    "gurugram": "gurgaon",
    "calcutta": "kolkata",
}

# A small, publicly known directory of cyber-crime reporting contacts.
# Deliberately kept generic rather than inventing station-specific phone
# numbers: the one number included (1930) is India's real, publicly
# published National Cyber Crime Helpline. Everything else in this
# directory is a location entry for distance-ranking only; any
# station-specific contact details a deployment needs should be sourced
# from an official, verified state police directory before going live.
NATIONAL_CYBER_CRIME_HELPLINE = "1930"
NATIONAL_CYBER_CRIME_PORTAL = "cybercrime.gov.in"

CYBER_CELL_DIRECTORY: List[Dict[str, Any]] = [
    {"name": "Kolhapur Cyber Police Station", "city": "Kolhapur", "latitude": 16.7050, "longitude": 74.2433},
    {"name": "Pune Cyber Police Station", "city": "Pune", "latitude": 18.5204, "longitude": 73.8567},
    {"name": "Mumbai Cyber Police Station", "city": "Mumbai", "latitude": 19.0760, "longitude": 72.8777},
    {"name": "Nashik Cyber Police Station", "city": "Nashik", "latitude": 19.9975, "longitude": 73.7898},
    {"name": "Nagpur Cyber Police Station", "city": "Nagpur", "latitude": 21.1458, "longitude": 79.0882},
    {"name": "Solapur Cyber Police Station", "city": "Solapur", "latitude": 17.6599, "longitude": 75.9064},
]


def _normalize_city(raw: Optional[str]) -> Optional[str]:
    '''Module 3 helper: lowercases, strips, and resolves known aliases for a place name.'''
    if not raw:
        return None
    key = raw.strip().lower()
    return CITY_ALIASES.get(key, key)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    '''Great-circle distance between two lat/lon points, in kilometres.'''
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def compass_direction(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    '''Coarse 8-point compass direction from point 1 to point 2, used to describe spread direction in plain language.'''
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    if abs(d_lat) < 1e-6 and abs(d_lon) < 1e-6:
        return "Stationary"
    vertical = "North" if d_lat > 0 else "South"
    horizontal = "East" if d_lon > 0 else "West"
    if abs(d_lat) < 0.05:
        return horizontal
    if abs(d_lon) < 0.05:
        return vertical
    return f"{vertical}-{horizontal}"

# ## 4. Input Contract - Geo Case Record


#
# A GeoCaseRecord is the shape Notebook 7 expects, assembled from Notebook
# 4 (address / GPS / timestamp), Notebook 2 (fraud type / risk), and
# Notebook 6 (campaign_id / community_id / connected-case context).
# Notebook 7 does not recompute any of those; it only consumes them.


@dataclass
class GeoCaseRecord:
    case_id: str
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    fraud_type: Optional[str] = None
    risk_score: float = 0.0                 # network-adjusted risk from Notebook 6 where available, else Notebook 2's score
    amount_involved: float = 0.0
    timestamp: Optional[str] = None
    campaign_id: Optional[str] = None       # from Notebook 6, optional
    community_id: Optional[str] = None      # from Notebook 6, optional
    is_mule_location: bool = False          # true if a money-mule account from Notebook 6 is tied to this case


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None

# ## 5. Module 1 - Location Intelligence Collector


def collect_locations(cases: List[GeoCaseRecord]) -> List[GeoCaseRecord]:
    '''
    Module 1 entry point. Normalizes the city field on every case (Module
    3's alias resolution folded in here since it must happen before
    geocoding) and returns the cases unchanged otherwise. This is a thin,
    explicit first pass so every downstream module can assume city names
    are already canonical.
    '''
    for case in cases:
        case.city = _normalize_city(case.city)
    logger.info("Location collection complete. cases=%d", len(cases))
    return cases

# ## 6. Module 2 - Geocoder


def geocode_cases(cases: List[GeoCaseRecord]) -> Dict[str, int]:
    '''
    Module 2 entry point. Fills in latitude/longitude for any case that
    does not already carry coordinates, using the offline gazetteer.
    Cases whose city is not in the gazetteer and which also lack explicit
    coordinates are left ungeocoded; they still flow through the
    non-spatial modules (time intelligence, resource recommendations by
    named city) but are excluded from hotspot clustering and mapping.
    Returns a small stats dict for the pipeline log.
    '''
    stats = {"already_had_coordinates": 0, "geocoded_from_city": 0, "unresolved": 0}
    for case in cases:
        if case.latitude is not None and case.longitude is not None:
            stats["already_had_coordinates"] += 1
            continue
        coords = CITY_COORDINATES.get(case.city) if case.city else None
        if coords:
            case.latitude, case.longitude = coords
            stats["geocoded_from_city"] += 1
        else:
            stats["unresolved"] += 1
            logger.warning("Could not geocode case %s (city=%r); excluded from spatial modules.", case.case_id, case.city)
    logger.info("Geocoding complete. %s", stats)
    return stats


def _district_for(case: GeoCaseRecord) -> str:
    '''Resolves a case's district for aggregation, falling back to its city, then "Unknown".'''
    if case.city and case.city in CITY_TO_DISTRICT:
        return CITY_TO_DISTRICT[case.city]
    return case.city.title() if case.city else "Unknown"

# ## 7. Module 4 - Fraud Hotspot Detection (haversine DBSCAN)


#
# A small, dependency-free DBSCAN implementation over haversine distance.
# This avoids requiring scikit-learn purely for one clustering call, and
# keeps the notebook runnable in a minimal environment. Complexity is
# O(n^2) in the number of geocoded cases, which is acceptable at the case
# volumes this kind of hackathon demo (and most real regional deployments)
# operate at.


def _region_query(points: List[Tuple[float, float]], idx: int, eps_km: float) -> List[int]:
    lat_i, lon_i = points[idx]
    neighbors = []
    for j, (lat_j, lon_j) in enumerate(points):
        if j == idx:
            continue
        if haversine_km(lat_i, lon_i, lat_j, lon_j) <= eps_km:
            neighbors.append(j)
    return neighbors


def _dbscan_haversine(points: List[Tuple[float, float]], eps_km: float, min_samples: int) -> List[int]:
    '''Returns a cluster label per point: -1 for noise, otherwise a 0-indexed cluster id.'''
    n = len(points)
    labels: List[Optional[int]] = [None] * n
    visited = [False] * n
    cluster_id = -1

    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        neighbors = _region_query(points, i, eps_km)
        if len(neighbors) < min_samples:
            labels[i] = -1
            continue

        cluster_id += 1
        labels[i] = cluster_id
        seeds = list(neighbors)
        k = 0
        while k < len(seeds):
            j = seeds[k]
            if not visited[j]:
                visited[j] = True
                j_neighbors = _region_query(points, j, eps_km)
                if len(j_neighbors) >= min_samples:
                    seeds.extend(x for x in j_neighbors if x not in seeds)
            if labels[j] is None or labels[j] == -1:
                labels[j] = cluster_id
            k += 1

    return [lbl if lbl is not None else -1 for lbl in labels]


def detect_hotspots(cases: List[GeoCaseRecord]) -> List[Dict[str, Any]]:
    '''
    Module 4 entry point. Clusters geocoded cases by physical proximity
    (Config.HOTSPOT_EPS_KM radius, Config.HOTSPOT_MIN_CASES minimum size)
    and reports each resulting cluster as a named hotspot with case count,
    total amount, average risk, dominant fraud type, and a priority level.
    '''
    geocoded = [c for c in cases if c.latitude is not None and c.longitude is not None]
    if len(geocoded) < CONFIG.HOTSPOT_MIN_CASES:
        return []

    points = [(c.latitude, c.longitude) for c in geocoded]
    labels = _dbscan_haversine(points, CONFIG.HOTSPOT_EPS_KM, CONFIG.HOTSPOT_MIN_CASES)

    clusters: Dict[int, List[GeoCaseRecord]] = defaultdict(list)
    for case, label in zip(geocoded, labels):
        if label >= 0:
            clusters[label].append(case)

    hotspots: List[Dict[str, Any]] = []
    for idx, (_, members) in enumerate(
        sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True), start=1
    ):
        lats = [m.latitude for m in members]
        lons = [m.longitude for m in members]
        centroid = (sum(lats) / len(lats), sum(lons) / len(lons))

        fraud_types = [m.fraud_type for m in members if m.fraud_type]
        dominant_fraud = max(set(fraud_types), key=fraud_types.count) if fraud_types else "Unclassified"

        total_amount = sum(m.amount_involved for m in members)
        avg_risk = round(sum(m.risk_score for m in members) / len(members), 1)
        city_counts = defaultdict(int)
        for m in members:
            if m.city:
                city_counts[m.city.title()] += 1
        primary_city = max(city_counts, key=city_counts.get) if city_counts else "Unknown"

        case_count = len(members)
        if case_count >= CONFIG.HOTSPOT_CRITICAL_MIN_CASES:
            priority = "Critical"
        elif case_count >= CONFIG.HOTSPOT_HIGH_MIN_CASES:
            priority = "High"
        else:
            priority = "Medium"

        confidence = round(min(97.0, 100 * min(1.0, case_count / (CONFIG.HOTSPOT_CRITICAL_MIN_CASES * 1.5))), 1)

        hotspots.append({
            "hotspot_id": f"HOTSPOT-{idx:03d}",
            "primary_city": primary_city,
            "district": _district_for(members[0]),
            "centroid_latitude": round(centroid[0], 4),
            "centroid_longitude": round(centroid[1], 4),
            "case_count": case_count,
            "case_ids": sorted(m.case_id for m in members),
            "dominant_fraud": dominant_fraud,
            "total_amount_involved": round(total_amount, 2),
            "average_risk": avg_risk,
            "priority": priority,
            "confidence": confidence,
            "mule_locations_present": any(m.is_mule_location for m in members),
        })

    logger.info("Hotspot detection complete. hotspots_found=%d", len(hotspots))
    return hotspots

# ## 8. Module 6 - Time Intelligence


def _time_bucket(hour: int) -> str:
    for start, end, label in CONFIG.TIME_BUCKETS:
        if start <= hour < end:
            return label
    return "Unknown"


def analyze_time_intelligence(cases: List[GeoCaseRecord]) -> Dict[str, Any]:
    '''
    Module 6 entry point. Builds day-of-week and time-of-day distributions
    across all timestamped cases and reports the single peak day and peak
    time bucket, so a command center knows when to expect the next wave.
    '''
    weekday_counts: Dict[str, int] = defaultdict(int)
    bucket_counts: Dict[str, int] = defaultdict(int)
    timestamped = 0

    for case in cases:
        dt = _parse_timestamp(case.timestamp)
        if dt is None:
            continue
        timestamped += 1
        weekday_counts[dt.strftime("%A")] += 1
        bucket_counts[_time_bucket(dt.hour)] += 1

    peak_day = max(weekday_counts, key=weekday_counts.get) if weekday_counts else None
    peak_bucket = max(bucket_counts, key=bucket_counts.get) if bucket_counts else None

    return {
        "timestamped_cases": timestamped,
        "weekday_distribution": dict(weekday_counts),
        "time_of_day_distribution": dict(bucket_counts),
        "peak_day": peak_day,
        "peak_time_of_day": peak_bucket,
    }

# ## 9. Module 7 + Module 11 - Fraud Spread Intelligence / Campaign Geography


def analyze_campaign_spread(cases: List[GeoCaseRecord]) -> List[Dict[str, Any]]:
    '''
    Module 7 (spread direction/speed/trend) and Module 11 (campaign
    geography path) combined, since both operate on the same grouping:
    cases sharing a Notebook-6 campaign_id, ordered chronologically.
    Cases without a campaign_id are skipped here entirely; standalone
    geographic spread with no known campaign is out of scope for this
    module and is instead visible only at the district level (Module 8).
    '''
    by_campaign: Dict[str, List[GeoCaseRecord]] = defaultdict(list)
    for case in cases:
        if case.campaign_id:
            by_campaign[case.campaign_id].append(case)

    results: List[Dict[str, Any]] = []
    for campaign_id, members in by_campaign.items():
        timestamped = sorted(
            (c for c in members if _parse_timestamp(c.timestamp) is not None),
            key=lambda c: _parse_timestamp(c.timestamp),
        )
        if len(timestamped) < 1:
            continue

        # City path in chronological order, collapsing consecutive repeats
        # (e.g. three same-city cases in a row read as one stop, not three).
        path: List[str] = []
        path_coords: List[Tuple[float, float]] = []
        for c in timestamped:
            label = c.city.title() if c.city else "Unknown"
            if not path or path[-1] != label:
                path.append(label)
                if c.latitude is not None and c.longitude is not None:
                    path_coords.append((c.latitude, c.longitude))

        distinct_cities = len(set(path))
        direction = "Insufficient data"
        total_distance_km = 0.0
        if len(path_coords) >= 2:
            direction = compass_direction(*path_coords[0], *path_coords[-1])
            for a, b in zip(path_coords, path_coords[1:]):
                total_distance_km += haversine_km(a[0], a[1], b[0], b[1])

        first_dt = _parse_timestamp(timestamped[0].timestamp)
        last_dt = _parse_timestamp(timestamped[-1].timestamp)
        duration_days = max(0, (last_dt - first_dt).days) if first_dt and last_dt else 0
        speed_km_per_day = round(total_distance_km / duration_days, 2) if duration_days > 0 else None

        # Trend: compare case counts in the earlier half vs later half of
        # the campaign's timeline, same coarse-proxy approach Notebook 6
        # uses for its own growth_trend field, for consistency across engines.
        trend = "Insufficient data"
        if len(timestamped) >= 4:
            midpoint = len(timestamped) // 2
            earlier = midpoint
            later = len(timestamped) - midpoint
            if later > earlier * 1.1:
                trend = "Increasing"
            elif later < earlier * 0.9:
                trend = "Decreasing"
            else:
                trend = "Stable"

        results.append({
            "campaign_id": campaign_id,
            "linked_cases": [c.case_id for c in timestamped],
            "city_path": path,
            "distinct_cities_touched": distinct_cities,
            "shows_geographic_spread": distinct_cities >= CONFIG.SPREAD_MIN_CITIES,
            "spread_direction": direction,
            "spread_speed_km_per_day": speed_km_per_day,
            "total_distance_km": round(total_distance_km, 1),
            "estimated_duration_days": duration_days,
            "trend": trend,
            "first_seen": first_dt.isoformat() if first_dt else None,
            "latest_seen": last_dt.isoformat() if last_dt else None,
        })

    logger.info("Campaign spread analysis complete. campaigns_analyzed=%d", len(results))
    return results

# ## 10. Module 8 - District Risk Ranking


def rank_district_risk(cases: List[GeoCaseRecord]) -> List[Dict[str, Any]]:
    '''
    Module 8 entry point. Aggregates cases by district into a composite
    0-100 risk score blending case volume, money involved, growth
    (recent activity vs earlier activity within the district), and
    average case severity (risk_score carried in from Notebook 2/6).
    Scores are min-max normalized across districts present in this batch
    so the ranking is always relative to what is actually being observed,
    rather than pinned to fixed absolute cutoffs that might never trigger
    on a small demo dataset.
    '''
    by_district: Dict[str, List[GeoCaseRecord]] = defaultdict(list)
    for case in cases:
        by_district[_district_for(case)].append(case)

    raw_rows: List[Dict[str, Any]] = []
    for district, members in by_district.items():
        case_count = len(members)
        total_amount = sum(m.amount_involved for m in members)
        avg_severity = sum(m.risk_score for m in members) / case_count if case_count else 0.0

        timestamped = sorted(
            (m for m in members if _parse_timestamp(m.timestamp) is not None),
            key=lambda m: _parse_timestamp(m.timestamp),
        )
        growth_rate = 0.0
        if len(timestamped) >= 4:
            midpoint = len(timestamped) // 2
            earlier_count = midpoint
            later_count = len(timestamped) - midpoint
            growth_rate = (later_count - earlier_count) / max(1, earlier_count)

        raw_rows.append({
            "district": district,
            "case_count": case_count,
            "total_amount_involved": total_amount,
            "average_severity": avg_severity,
            "growth_rate": growth_rate,
            "case_ids": sorted(m.case_id for m in members),
            "campaigns_present": sorted({m.campaign_id for m in members if m.campaign_id}),
            "communities_present": sorted({m.community_id for m in members if m.community_id}),
            "mule_locations_present": any(m.is_mule_location for m in members),
        })

    def _minmax(values: List[float]) -> Tuple[float, float]:
        return (min(values), max(values)) if values else (0.0, 1.0)

    case_min, case_max = _minmax([r["case_count"] for r in raw_rows])
    amt_min, amt_max = _minmax([r["total_amount_involved"] for r in raw_rows])
    growth_min, growth_max = _minmax([r["growth_rate"] for r in raw_rows])
    sev_min, sev_max = _minmax([r["average_severity"] for r in raw_rows])

    def _norm(v: float, lo: float, hi: float) -> float:
        return (v - lo) / (hi - lo) if hi > lo else (1.0 if hi > 0 else 0.0)

    ranked: List[Dict[str, Any]] = []
    for row in raw_rows:
        composite = 100 * (
            CONFIG.DISTRICT_RISK_CASE_WEIGHT * _norm(row["case_count"], case_min, case_max)
            + CONFIG.DISTRICT_RISK_AMOUNT_WEIGHT * _norm(row["total_amount_involved"], amt_min, amt_max)
            + CONFIG.DISTRICT_RISK_GROWTH_WEIGHT * _norm(row["growth_rate"], growth_min, growth_max)
            + CONFIG.DISTRICT_RISK_SEVERITY_WEIGHT * _norm(row["average_severity"], sev_min, sev_max)
        )
        composite = round(composite, 1)

        if composite >= CONFIG.DISTRICT_PRIORITY_CRITICAL_MIN:
            priority = "Critical"
        elif composite >= CONFIG.DISTRICT_PRIORITY_HIGH_MIN:
            priority = "High"
        elif composite >= CONFIG.DISTRICT_PRIORITY_MEDIUM_MIN:
            priority = "Medium"
        else:
            priority = "Low"

        ranked.append({
            **row,
            "total_amount_involved": round(row["total_amount_involved"], 2),
            "average_severity": round(row["average_severity"], 1),
            "growth_rate_pct": round(row["growth_rate"] * 100, 1),
            "composite_risk_score": composite,
            "priority": priority,
        })

    ranked.sort(key=lambda r: r["composite_risk_score"], reverse=True)
    logger.info("District risk ranking complete. districts_ranked=%d", len(ranked))
    return ranked

# ## 11. Module 12 - Predictive Hotspots


def predict_next_hotspots(district_ranking: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    '''
    Module 12 entry point. Flags districts that are not yet Critical but
    are growing fast (Config.PREDICTION_GROWTH_THRESHOLD) as likely next
    hotspots. This is deliberately a simple, explainable trend read - no
    deep learning, no external forecasting model - in keeping with the
    "simple trend analysis is enough for MVP" guidance for this module.
    '''
    predictions: List[Dict[str, Any]] = []
    for row in district_ranking:
        if row["priority"] == "Critical":
            continue
        if row["growth_rate_pct"] / 100.0 >= CONFIG.PREDICTION_GROWTH_THRESHOLD:
            predictions.append({
                "district": row["district"],
                "current_priority": row["priority"],
                "growth_rate_pct": row["growth_rate_pct"],
                "reason": (
                    f"{row['growth_rate_pct']:.0f}% case growth in the recent window "
                    f"against a current composite risk score of {row['composite_risk_score']}."
                ),
                "recommended_watch_level": "High" if row["priority"] == "Medium" else "Medium",
            })

    predictions.sort(key=lambda p: p["growth_rate_pct"], reverse=True)
    logger.info("Predictive hotspot analysis complete. districts_flagged=%d", len(predictions))
    return predictions

# ## 12. Module 9 - Resource Allocation Recommendation


def recommend_resources(
    district_ranking: List[Dict[str, Any]],
    hotspots: List[Dict[str, Any]],
    campaign_spread: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    '''
    Module 9 entry point. Turns the district ranking, hotspot list, and
    campaign spread analysis into a short, rule-based, explainable set of
    recommended actions per district - the kind of output a command
    center can act on directly rather than a raw risk number.
    '''
    spread_districts = set()
    for campaign in campaign_spread:
        if campaign["shows_geographic_spread"]:
            spread_districts.update(campaign["city_path"])

    recommendations: List[Dict[str, Any]] = []
    for row in district_ranking:
        actions: List[str] = []

        if row["priority"] == "Critical":
            actions.append("Deploy cyber cell / rapid response team immediately.")
            actions.append("Run a public awareness campaign targeted at this district.")
        elif row["priority"] == "High":
            actions.append("Increase cyber-crime desk staffing and monitoring.")
            actions.append("Coordinate an awareness campaign with local police stations.")
        elif row["priority"] == "Medium":
            actions.append("Maintain routine monitoring; schedule a periodic review.")
        else:
            actions.append("No immediate action required; continue standard monitoring.")

        if row["mule_locations_present"]:
            actions.append("Notify partner banks to review and freeze linked mule accounts.")

        if row["campaigns_present"]:
            actions.append("Notify telecom providers to flag phone numbers tied to active campaigns in this district.")

        if any(row["district"].lower() in d.lower() or d.lower() in row["district"].lower() for d in spread_districts):
            actions.append("Alert neighboring districts on the campaign's spread path to pre-position resources.")

        recommendations.append({
            "district": row["district"],
            "priority": row["priority"],
            "actions": actions,
        })

    logger.info("Resource recommendations generated for %d district(s).", len(recommendations))
    return recommendations

# ## 13. Module 10 - Nearby Cyber Police Recommendation


def find_nearest_cyber_cells(hotspots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    '''
    Module 10 entry point. For each hotspot, finds the nearest entry in
    the (small, offline) cyber-cell directory by haversine distance and
    returns it alongside the real, publicly published National Cyber
    Crime Helpline. Station-specific phone numbers are intentionally not
    fabricated here; a production deployment should populate verified
    contact numbers from an official state police directory.
    '''
    results: List[Dict[str, Any]] = []
    for hotspot in hotspots:
        best = None
        best_distance = None
        for cell in CYBER_CELL_DIRECTORY:
            d = haversine_km(
                hotspot["centroid_latitude"], hotspot["centroid_longitude"],
                cell["latitude"], cell["longitude"],
            )
            if d <= CONFIG.MAX_CYBER_CELL_SEARCH_KM and (best_distance is None or d < best_distance):
                best, best_distance = cell, d

        results.append({
            "hotspot_id": hotspot["hotspot_id"],
            "nearest_cyber_cell": best["name"] if best else None,
            "nearest_cyber_cell_city": best["city"] if best else None,
            "distance_km": round(best_distance, 1) if best_distance is not None else None,
            "national_helpline": NATIONAL_CYBER_CRIME_HELPLINE,
            "national_portal": NATIONAL_CYBER_CRIME_PORTAL,
            "note": "Station-specific contact numbers must be verified against the official state police directory before use.",
        })

    return results

# ## 14. Module 13 - Command Center Dashboard


def build_command_center_dashboard(
    cases: List[GeoCaseRecord],
    hotspots: List[Dict[str, Any]],
    district_ranking: List[Dict[str, Any]],
    campaign_spread: List[Dict[str, Any]],
    predicted_hotspots: List[Dict[str, Any]],
    time_intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    '''Module 13 entry point. Plain rollup of everything a command-center operator needs at a glance.'''
    total_amount = round(sum(c.amount_involved for c in cases), 2)
    critical_districts = [r["district"] for r in district_ranking if r["priority"] == "Critical"]

    summary_lines: List[str] = []
    if hotspots:
        top = hotspots[0]
        summary_lines.append(
            f"Top hotspot is {top['primary_city']} ({top['hotspot_id']}) with {top['case_count']} case(s), "
            f"priority {top['priority']}, dominant pattern: {top['dominant_fraud']}."
        )
    else:
        summary_lines.append("No geographic hotspot met the minimum case threshold yet.")

    if critical_districts:
        summary_lines.append(f"Critical-priority districts: {', '.join(critical_districts)}.")

    spreading = [c for c in campaign_spread if c["shows_geographic_spread"]]
    if spreading:
        lead = spreading[0]
        summary_lines.append(
            f"{len(spreading)} campaign(s) show geographic spread; {lead['campaign_id']} is moving "
            f"{lead['spread_direction']} through {' -> '.join(lead['city_path'])} (trend: {lead['trend']})."
        )

    if predicted_hotspots:
        top_pred = predicted_hotspots[0]
        summary_lines.append(
            f"{top_pred['district']} is flagged as a likely next hotspot ({top_pred['reason']})."
        )

    if time_intelligence.get("peak_day") and time_intelligence.get("peak_time_of_day"):
        summary_lines.append(
            f"Peak fraud activity observed on {time_intelligence['peak_day']}s during the "
            f"{time_intelligence['peak_time_of_day']} window."
        )

    return {
        "total_cases": len(cases),
        "total_amount_involved": total_amount,
        "total_hotspots": len(hotspots),
        "critical_districts": critical_districts,
        "districts_monitored": len(district_ranking),
        "campaigns_with_geographic_spread": len(spreading),
        "predicted_hotspots_count": len(predicted_hotspots),
        "summary": summary_lines,
    }

# ## 15. Module 5 + Module 14 - Heatmap / Map Visualization


_PRIORITY_COLORS = {"Critical": "#d62728", "High": "#ff7f0e", "Medium": "#f2c744", "Low": "#2ca02c"}


def build_map_visualization(
    cases: List[GeoCaseRecord],
    hotspots: List[Dict[str, Any]],
    output_path: str,
) -> Optional[str]:
    '''
    Module 5 (heatmap-style density coloring) and Module 14 (map
    visualization: case points, hotspot centroids, cyber cell locations)
    combined into a single static image. Skips silently (returns None) if
    matplotlib is not installed, matching Notebook 6's degrade-gracefully
    pattern - the JSON intelligence package remains fully usable either way.
    '''
    if not _MATPLOTLIB_AVAILABLE:
        logger.info("matplotlib not available; skipping map visualization.")
        return None

    geocoded = [c for c in cases if c.latitude is not None and c.longitude is not None]
    if not geocoded:
        return None

    plt.figure(figsize=(11, 9))

    # Base layer: every case as a small point, colored by its own risk score.
    xs = [c.longitude for c in geocoded]
    ys = [c.latitude for c in geocoded]
    risks = [c.risk_score for c in geocoded]
    scatter = plt.scatter(xs, ys, c=risks, cmap="YlOrRd", s=40, alpha=0.75, edgecolors="none", label="Cases")
    plt.colorbar(scatter, label="Case risk score")

    # Hotspot layer: larger, outlined markers at each hotspot centroid,
    # colored by priority so the highest-priority clusters pop out.
    for hotspot in hotspots:
        color = _PRIORITY_COLORS.get(hotspot["priority"], "#7f7f7f")
        plt.scatter(
            hotspot["centroid_longitude"], hotspot["centroid_latitude"],
            s=250 + 40 * hotspot["case_count"], facecolors="none", edgecolors=color, linewidths=2.5,
        )
        plt.annotate(
            f"{hotspot['hotspot_id']}\n{hotspot['primary_city']}",
            (hotspot["centroid_longitude"], hotspot["centroid_latitude"]),
            fontsize=8, ha="center", va="bottom",
        )

    # Cyber cell layer: small black markers for reference.
    for cell in CYBER_CELL_DIRECTORY:
        plt.scatter(cell["longitude"], cell["latitude"], marker="^", c="black", s=60)

    plt.title("Geospatial Fraud Intelligence Map")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    logger.info("Map visualization saved to %s", output_path)
    return output_path

# ## 16. Module 15b - Command Center Report (PDF, with plain-text fallback)


#
# Mirrors Notebook 6's Module 17 police intelligence report: a single,
# one-click document a command-center officer can hand upward. Uses
# `reportlab` when available and degrades to a plain-text report (same
# content, no layout) when it is not.

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
    '''Shared content builder used by both the PDF and plain-text report paths.'''
    lines: List[str] = []
    lines.append(f"GEOSPATIAL CRIME PATTERN INTELLIGENCE REPORT - {package['package_id']}")
    lines.append("")
    lines.append("COMMAND CENTER SUMMARY")
    lines.extend(f"  - {line}" for line in package["dashboard"]["summary"])
    lines.append("")

    if package["hotspots"]:
        lines.append("FRAUD HOTSPOTS")
        for h in package["hotspots"]:
            lines.append(
                f"  - {h['hotspot_id']} ({h['primary_city']}, {h['district']}): {h['case_count']} case(s), "
                f"priority {h['priority']}, Rs {h['total_amount_involved']:,.0f}, pattern: {h['dominant_fraud']}"
            )
        lines.append("")

    if package["district_risk"]:
        lines.append("DISTRICT RISK RANKING")
        for r in package["district_risk"]:
            lines.append(
                f"  - {r['district']}: priority {r['priority']}, score {r['composite_risk_score']}, "
                f"{r['case_count']} case(s), growth {r['growth_rate_pct']}%"
            )
        lines.append("")

    if package["predicted_hotspots"]:
        lines.append("PREDICTED NEXT HOTSPOTS")
        for p in package["predicted_hotspots"]:
            lines.append(f"  - {p['district']}: {p['reason']}")
        lines.append("")

    if package["campaign_spread"]:
        lines.append("CAMPAIGN GEOGRAPHIC SPREAD")
        for c in package["campaign_spread"]:
            lines.append(
                f"  - {c['campaign_id']}: {' -> '.join(c['city_path'])} "
                f"(direction {c['spread_direction']}, trend {c['trend']})"
            )
        lines.append("")

    if package["resource_recommendations"]:
        lines.append("RESOURCE RECOMMENDATIONS")
        for rec in package["resource_recommendations"]:
            lines.append(f"  - {rec['district']} ({rec['priority']}):")
            for action in rec["actions"]:
                lines.append(f"      * {action}")
        lines.append("")

    if package["nearest_cyber_cells"]:
        lines.append("NEAREST CYBER CELLS PER HOTSPOT")
        for entry in package["nearest_cyber_cells"]:
            lines.append(
                f"  - {entry['hotspot_id']}: {entry['nearest_cyber_cell']} "
                f"({entry['distance_km']} km) | Helpline {entry['national_helpline']} | {entry['national_portal']}"
            )
        lines.append("")

    lines.append(f"OVERALL PACKAGE CONFIDENCE: {package['confidence']}%")
    return lines


def generate_command_center_report(package: Dict[str, Any], output_path: str) -> str:
    '''
    Module 15b entry point. Writes a formatted PDF when reportlab is
    available; otherwise writes an equivalent plain-text report (path
    extension swapped to .txt) so the report is never silently lost.
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

    story.append(Paragraph(f"Geospatial Crime Pattern Intelligence Report - {package['package_id']}", title_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Command Center Summary", heading_style))
    for line in package["dashboard"]["summary"]:
        story.append(Paragraph(line, body_style))

    if package["hotspots"]:
        story.append(Paragraph("Fraud Hotspots", heading_style))
        rows = [["Hotspot", "City", "Cases", "Priority", "Amount (Rs)", "Pattern"]]
        for h in package["hotspots"]:
            rows.append([h["hotspot_id"], h["primary_city"], str(h["case_count"]), h["priority"],
                         f"{h['total_amount_involved']:,.0f}", h["dominant_fraud"]])
        table = Table(rows, colWidths=[2.4 * cm, 2.6 * cm, 1.6 * cm, 2 * cm, 3 * cm, 3.4 * cm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]))
        story.append(table)

    if package["district_risk"]:
        story.append(Paragraph("District Risk Ranking", heading_style))
        rows = [["District", "Priority", "Score", "Cases", "Growth %"]]
        for r in package["district_risk"]:
            rows.append([r["district"], r["priority"], str(r["composite_risk_score"]),
                         str(r["case_count"]), f"{r['growth_rate_pct']}%"])
        table = Table(rows, colWidths=[3.6 * cm, 2.4 * cm, 2.2 * cm, 2 * cm, 2.4 * cm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ]))
        story.append(table)

    if package["predicted_hotspots"]:
        story.append(Paragraph("Predicted Next Hotspots", heading_style))
        for p in package["predicted_hotspots"]:
            story.append(Paragraph(f"{p['district']}: {p['reason']}", body_style))

    if package["campaign_spread"]:
        story.append(Paragraph("Campaign Geographic Spread", heading_style))
        for c in package["campaign_spread"]:
            story.append(Paragraph(
                f"{c['campaign_id']}: {' -> '.join(c['city_path'])} "
                f"(direction {c['spread_direction']}, trend {c['trend']})", body_style,
            ))

    if package["resource_recommendations"]:
        story.append(Paragraph("Resource Recommendations", heading_style))
        for rec in package["resource_recommendations"]:
            story.append(Paragraph(f"<b>{rec['district']}</b> ({rec['priority']})", body_style))
            for action in rec["actions"]:
                story.append(Paragraph(f"- {action}", body_style))

    if package.get("map_visualization") and os.path.exists(package["map_visualization"]):
        story.append(PageBreak())
        story.append(Paragraph("Geospatial Map", heading_style))
        story.append(RLImage(package["map_visualization"], width=16 * cm, height=13 * cm))

    story.append(Paragraph("Overall Package Confidence", heading_style))
    story.append(Paragraph(f"{package['confidence']}%", body_style))

    doc.build(story)
    logger.info("Command center report saved to %s", output_path)
    return output_path

# ## 17. Module 15 - Geospatial Intelligence Package (Orchestration)


def build_audit_log(cases: List[GeoCaseRecord]) -> Dict[str, Any]:
    '''Hashes the sorted set of case ids currently processed, for tamper-evident audit purposes.'''
    case_ids_sorted = sorted(c.case_id for c in cases)
    digest_input = json.dumps(case_ids_sorted, sort_keys=True).encode("utf-8")
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_set_hash": hashlib.sha256(digest_input).hexdigest(),
        "total_cases": len(case_ids_sorted),
        "notebook_version": CONFIG.NOTEBOOK_VERSION,
    }


def _estimate_confidence(cases: List[GeoCaseRecord], geocode_stats: Dict[str, int]) -> float:
    '''
    Overall package confidence grows with sample size and with how much of
    the input was actually geocodable - a package built mostly from
    unresolved locations is a weaker claim than one built on solid coordinates.
    '''
    if not cases:
        return CONFIG.MIN_PACKAGE_CONFIDENCE
    geocoded_fraction = 1 - (geocode_stats.get("unresolved", 0) / len(cases))
    volume_support = min(1.0, len(cases) / 20.0)
    raw = 100 * (0.6 * geocoded_fraction + 0.4 * volume_support)
    return round(min(CONFIG.MAX_PACKAGE_CONFIDENCE, max(CONFIG.MIN_PACKAGE_CONFIDENCE, raw)), 1)


def analyze_geospatial_intelligence(
    cases: List[GeoCaseRecord],
    save_visualization: bool = True,
    generate_report: bool = True,
    visualization_dir: str = "/tmp/notebook7_maps",
    report_dir: str = "/tmp/notebook7_reports",
) -> Dict[str, Any]:
    '''
    Notebook 7 orchestration - Modules 1-15 combined.

    Normalizes and geocodes every case, detects hotspots, builds time
    intelligence, analyzes campaign geographic spread, ranks districts by
    composite risk, predicts likely next hotspots, generates resource
    recommendations, finds the nearest cyber cell per hotspot, assembles
    a command-center dashboard, renders a map visualization, and produces
    a one-click command-center report - then returns the restructured
    Geospatial Intelligence Package that Notebook 3 consumes as one more
    signal when deciding the final action on a case.
    '''
    stages: List[Dict[str, str]] = []

    try:
        if not cases:
            raise GeospatialIntelligenceError("No case records were provided to analyze_geospatial_intelligence().")

        cases = collect_locations(cases)
        stages.append({"stage": "Location Collection", "summary": f"{len(cases)} case(s) normalized"})

        geocode_stats = geocode_cases(cases)
        stages.append({"stage": "Geocoding", "summary": str(geocode_stats)})

        hotspots = detect_hotspots(cases)
        stages.append({"stage": "Hotspot Detection", "summary": f"{len(hotspots)} hotspot(s) found"})

        time_intelligence = analyze_time_intelligence(cases)
        stages.append({
            "stage": "Time Intelligence",
            "summary": f"peak_day={time_intelligence['peak_day']} peak_time={time_intelligence['peak_time_of_day']}",
        })

        campaign_spread = analyze_campaign_spread(cases)
        stages.append({"stage": "Campaign Spread / Geography", "summary": f"{len(campaign_spread)} campaign(s) analyzed"})

        district_ranking = rank_district_risk(cases)
        stages.append({"stage": "District Risk Ranking", "summary": f"{len(district_ranking)} district(s) ranked"})

        predicted_hotspots = predict_next_hotspots(district_ranking)
        stages.append({"stage": "Predictive Hotspots", "summary": f"{len(predicted_hotspots)} district(s) flagged"})

        resource_recommendations = recommend_resources(district_ranking, hotspots, campaign_spread)
        stages.append({"stage": "Resource Recommendation", "summary": f"{len(resource_recommendations)} district(s) covered"})

        nearest_cyber_cells = find_nearest_cyber_cells(hotspots)
        stages.append({"stage": "Nearest Cyber Cell Lookup", "summary": f"{len(nearest_cyber_cells)} hotspot(s) matched"})

        dashboard = build_command_center_dashboard(
            cases, hotspots, district_ranking, campaign_spread, predicted_hotspots, time_intelligence
        )
        stages.append({"stage": "Command Center Dashboard", "summary": f"{dashboard['total_cases']} case(s) summarized"})

        map_path = None
        if save_visualization:
            os.makedirs(visualization_dir, exist_ok=True)
            suffix = uuid.uuid4().hex[:8]
            map_path = build_map_visualization(cases, hotspots, os.path.join(visualization_dir, f"geo_map_{suffix}.png"))
        stages.append({"stage": "Map Visualization", "summary": map_path or "skipped (matplotlib unavailable)"})

        confidence = _estimate_confidence(cases, geocode_stats)
        audit_log = build_audit_log(cases)

        package: Dict[str, Any] = {
            "package_id": f"GEO-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}",
            "hotspots": hotspots,
            "district_risk": district_ranking,
            "predicted_hotspots": predicted_hotspots,
            "campaign_spread": campaign_spread,
            "resource_recommendations": resource_recommendations,
            "nearest_cyber_cells": nearest_cyber_cells,
            "time_intelligence": time_intelligence,
            "dashboard": dashboard,
            "map_visualization": map_path,
            "geocode_stats": geocode_stats,
            "confidence": confidence,
            "pipeline_stages": stages,
            "audit": audit_log,
            "next_engine": "Decision Intelligence Engine",
        }

        report_path = None
        if generate_report:
            os.makedirs(report_dir, exist_ok=True)
            suffix = uuid.uuid4().hex[:8]
            report_path = generate_command_center_report(
                package, os.path.join(report_dir, f"command_center_report_{suffix}.pdf")
            )
        package["command_center_report"] = report_path
        stages.append({"stage": "Command Center Report Generation", "summary": report_path or "skipped"})
        package["pipeline_stages"] = stages

        logger.info(
            "Geospatial intelligence analysis complete. cases=%d hotspots=%d districts=%d confidence=%s",
            len(cases), len(hotspots), len(district_ranking), confidence,
        )
        return package

    except GeospatialIntelligenceError:
        raise
    except Exception as exc:
        logger.exception("Notebook 7 pipeline failed.")
        raise GeospatialIntelligenceError(f"Notebook 7 pipeline failed: {exc}") from exc

# ## 18. Synthetic Case Generation and Deterministic Test Suite


#
# Real geo-tagged fraud data is not bundled with this notebook. To
# demonstrate and test the full pipeline deterministically, this section
# synthesizes a set of cases that model one geographically spreading
# "Digital Arrest" campaign moving Kolhapur -> Pune -> Mumbai -> Nashik
# (west to east / north), plus a dense but stationary hotspot in Nagpur,
# plus a couple of genuinely isolated cases. This is a pipeline test
# fixture, not a claim about any real investigation.


def _build_synthetic_cases() -> List[GeoCaseRecord]:
    cases: List[GeoCaseRecord] = []
    base_time = datetime(2026, 7, 1, tzinfo=timezone.utc)

    # --- A spreading campaign: 8 cases moving through 4 cities over time,
    # sharing campaign_id CAMPAIGN-01, with escalating case density in the
    # later cities so trend detection has something to find. ---
    spread_cities = ["Kolhapur", "Kolhapur", "Pune", "Pune", "Pune", "Mumbai", "Mumbai", "Nashik"]
    for i, city in enumerate(spread_cities, start=1):
        cases.append(GeoCaseRecord(
            case_id=f"CASE-S{i:03d}",
            city=city,
            state="Maharashtra",
            fraud_type="Digital Arrest",
            risk_score=70.0 + i,
            amount_involved=40000.0 + i * 2000,
            timestamp=base_time.replace(day=min(28, base_time.day + i)).isoformat(),
            campaign_id="CAMPAIGN-01",
            is_mule_location=(i == 4),
        ))

    # --- A dense, stationary hotspot: 6 unrelated-campaign cases clustered
    # in Nagpur within the same short window, to exercise Module 4 on a
    # single-city cluster rather than a spreading one. ---
    for i in range(1, 7):
        cases.append(GeoCaseRecord(
            case_id=f"CASE-N{i:03d}",
            city="Nagpur",
            state="Maharashtra",
            fraud_type="UPI Fraud",
            risk_score=60.0 + i,
            amount_involved=15000.0 + i * 1500,
            timestamp=base_time.replace(day=min(28, base_time.day + i), hour=(10 + i) % 24).isoformat(),
        ))

    # --- Two genuinely isolated, low-volume cases in cities that should
    # not form hotspots and should rank as Low/Medium priority districts. ---
    cases.append(GeoCaseRecord(
        case_id="CASE-ISO-001",
        city="Satara",
        state="Maharashtra",
        fraud_type="Romance Scam",
        risk_score=40.0,
        amount_involved=12000.0,
        timestamp=base_time.replace(day=10).isoformat(),
    ))
    cases.append(GeoCaseRecord(
        case_id="CASE-ISO-002",
        city="Sangli",
        state="Maharashtra",
        fraud_type="Job Scam",
        risk_score=35.0,
        amount_involved=8000.0,
        timestamp=base_time.replace(day=12).isoformat(),
    ))

    # --- One case with an unresolvable city, to exercise the geocoder's
    # graceful-degradation path. ---
    cases.append(GeoCaseRecord(
        case_id="CASE-UNRESOLVED-001",
        city="SomeVillageNotInGazetteer",
        state="Maharashtra",
        fraud_type="Lottery Scam",
        risk_score=45.0,
        amount_involved=5000.0,
        timestamp=base_time.replace(day=14).isoformat(),
    ))

    return cases


def run_notebook7_test_suite() -> Dict[str, Any]:
    print("=== Notebook 7 Test Suite: synthetic geospatial fraud data ===\n")

    cases = _build_synthetic_cases()
    checks: List[bool] = []

    def _check(label: str, actual: Any, expected: Any) -> None:
        ok = actual == expected
        checks.append(ok)
        print(f"    [{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")

    def _check_true(label: str, condition: bool) -> None:
        checks.append(condition)
        print(f"    [{'PASS' if condition else 'FAIL'}] {label}")

    print("--- Running full geospatial intelligence pipeline ---")
    package = analyze_geospatial_intelligence(cases)

    # --- Hotspot detection ---
    _check_true("at least one hotspot was detected", len(package["hotspots"]) > 0)
    nagpur_hotspot = next((h for h in package["hotspots"] if h["primary_city"] == "Nagpur"), None)
    _check_true("Nagpur cluster was detected as a hotspot", nagpur_hotspot is not None)
    if nagpur_hotspot:
        _check_true("Nagpur hotspot contains all 6 Nagpur cases", nagpur_hotspot["case_count"] == 6)

    # --- Geocoding ---
    _check_true("most cases were successfully geocoded", package["geocode_stats"]["geocoded_from_city"] >= 15)
    _check_true("the unresolvable city was left ungeocoded, not crashed", package["geocode_stats"]["unresolved"] >= 1)

    # --- Time intelligence ---
    _check_true("time intelligence identified a peak day", package["time_intelligence"]["peak_day"] is not None)
    _check_true("time intelligence identified a peak time-of-day bucket", package["time_intelligence"]["peak_time_of_day"] is not None)

    # --- Campaign spread ---
    _check_true("at least one campaign spread analysis was produced", len(package["campaign_spread"]) > 0)
    campaign_01 = next((c for c in package["campaign_spread"] if c["campaign_id"] == "CAMPAIGN-01"), None)
    _check_true("CAMPAIGN-01 was analyzed", campaign_01 is not None)
    if campaign_01:
        _check_true("CAMPAIGN-01 shows geographic spread across multiple cities", campaign_01["shows_geographic_spread"])
        _check("CAMPAIGN-01 city path matches expected chronological order",
               campaign_01["city_path"], ["Kolhapur", "Pune", "Mumbai", "Nashik"])
        _check_true("CAMPAIGN-01 spread direction was computed", campaign_01["spread_direction"] != "Insufficient data")

    # --- District risk ranking ---
    _check_true("district risk ranking was produced for multiple districts", len(package["district_risk"]) >= 4)
    top_district = package["district_risk"][0]
    _check_true("top-ranked district has the highest composite score in the list",
                all(top_district["composite_risk_score"] >= r["composite_risk_score"] for r in package["district_risk"]))
    _check_true("every district row carries a valid priority label",
                all(r["priority"] in ("Critical", "High", "Medium", "Low") for r in package["district_risk"]))

    # --- Predictive hotspots ---
    _check_true("predicted hotspots list was produced without error", isinstance(package["predicted_hotspots"], list))

    # --- Resource recommendations ---
    _check_true("resource recommendations were generated for every ranked district",
                len(package["resource_recommendations"]) == len(package["district_risk"]))
    nagpur_rec = next((r for r in package["resource_recommendations"] if r["district"] == "Nagpur"), None)
    _check_true("Nagpur has at least one recommended action", nagpur_rec is not None and len(nagpur_rec["actions"]) > 0)

    # --- Mule location signal propagates into district ranking and recommendations ---
    pune_district_row = next((r for r in package["district_risk"] if r["district"] == "Pune"), None)
    _check_true("Pune district row flags mule_locations_present", pune_district_row is not None and pune_district_row["mule_locations_present"])
    pune_rec = next((r for r in package["resource_recommendations"] if r["district"] == "Pune"), None)
    _check_true("Pune's recommendations mention notifying banks about mule accounts",
                pune_rec is not None and any("bank" in a.lower() for a in pune_rec["actions"]))

    # --- Nearest cyber cell lookup ---
    _check_true("nearest cyber cell entries were produced for every hotspot",
                len(package["nearest_cyber_cells"]) == len(package["hotspots"]))
    _check_true("nearest cyber cell entries carry the national helpline",
                all(e["national_helpline"] == NATIONAL_CYBER_CRIME_HELPLINE for e in package["nearest_cyber_cells"]))

    # --- Dashboard ---
    dashboard = package["dashboard"]
    _check("dashboard total_cases matches input case count", dashboard["total_cases"], len(cases))
    _check_true("dashboard summary has at least one line", len(dashboard["summary"]) > 0)

    # --- Package structure ---
    expected_keys = {
        "package_id", "hotspots", "district_risk", "predicted_hotspots", "campaign_spread",
        "resource_recommendations", "nearest_cyber_cells", "time_intelligence", "dashboard",
        "map_visualization", "geocode_stats", "confidence", "pipeline_stages", "audit",
        "next_engine", "command_center_report",
    }
    _check_true("package contains all expected top-level keys", expected_keys.issubset(set(package.keys())))
    _check("pipeline has 12 stages", len(package["pipeline_stages"]), 12)

    # --- Confidence bounds ---
    _check_true("overall package confidence is within configured bounds",
                CONFIG.MIN_PACKAGE_CONFIDENCE <= package["confidence"] <= CONFIG.MAX_PACKAGE_CONFIDENCE)

    # --- Command center report ---
    _check_true("command center report file was generated", package["command_center_report"] is not None)
    _check_true("command center report file exists on disk", os.path.exists(package["command_center_report"]))

    # --- Spatial normalization / alias resolution sanity check ---
    alias_case_a = GeoCaseRecord(case_id="CASE-ALIAS-A", city="Bombay", state="Maharashtra", risk_score=50.0)
    alias_case_b = GeoCaseRecord(case_id="CASE-ALIAS-B", city="mumbai", state="Maharashtra", risk_score=50.0)
    collect_locations([alias_case_a, alias_case_b])
    _check("differently-cased/aliased city names resolve to the same canonical value",
           alias_case_a.city, alias_case_b.city)

    # --- Haversine sanity check: Kolhapur to Pune is roughly 200-230 km ---
    kolhapur = CITY_COORDINATES["kolhapur"]
    pune = CITY_COORDINATES["pune"]
    distance = haversine_km(kolhapur[0], kolhapur[1], pune[0], pune[1])
    _check_true("haversine distance Kolhapur-Pune falls in a plausible range", 180.0 <= distance <= 260.0)

    print(f"\nSUMMARY: {sum(checks)}/{len(checks)} checks passed\n")

    print("Command center dashboard summary:")
    for line in dashboard["summary"]:
        print(f"  - {line}")

    print("\nPipeline stages:")
    for s in package["pipeline_stages"]:
        print(f"  {s['stage']:32s} | {s['summary']}")

    print("\nHotspots detected:")
    for h in package["hotspots"]:
        print(f"  {h['hotspot_id']:14s} {h['primary_city']:10s} cases={h['case_count']} priority={h['priority']}")

    print("\nDistrict risk ranking:")
    for r in package["district_risk"]:
        print(f"  {r['district']:24s} score={r['composite_risk_score']:6.1f} priority={r['priority']}")

    print("\nCampaign spread:")
    print(json.dumps(package["campaign_spread"], indent=2))

    print(f"\nMap visualization file: {package['map_visualization']}")
    print(f"Command center report file: {package['command_center_report']}")
    print(f"\nAudit log: {json.dumps(package['audit'], indent=2)}")

    return package


if __name__ == "__main__":
    run_notebook7_test_suite()