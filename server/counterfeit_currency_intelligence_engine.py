# Generated from: counterfeit_currency_intelligence_engine.ipynb
# Converted at: 2026-07-15T01:45:38.337Z
# Next step (optional): refactor into modules & generate tests with RunCell
# Quick start: pip install runcell

# # Counterfeit Currency Intelligence Engine
# 
# counterfeit_currency_intelligence_engine.py
# ET AI Hackathon 2026 - Digital Public Safety Platform (PS6)
# Notebook 5 - Counterfeit Currency Intelligence Engine (Revision 2)
# 
# Mission (one sentence):
# Analyze uploaded currency images, verify important RBI security features,
# detect counterfeit indicators, explain why a note appears genuine or
# suspicious, estimate confidence, and return structured intelligence.
# 
# What this notebook is NOT:
#   - It does not detect Digital Arrest, UPI Fraud, Romance Scams, or any
#     text-based fraud pattern. That is Notebook 2's job.
#   - It does not decide what action to take. That is Notebook 3's job.
#   - It is not a black-box "Fake / Genuine" classifier. Every verdict is
#     backed by a per-feature breakdown and a plain-language explanation.
# 
# Position in the pipeline:
# 
#   Citizen uploads a currency image
#           |
#           v
#   Notebook 4 - Digital Evidence Intelligence Engine
#     (classifies the evidence_type as "Currency Image")
#           |
#           v
#   Notebook 5 - Counterfeit Currency Intelligence Engine   <- this file
#     (only invoked when evidence_type == "Currency Image"; skipped otherwise)
#           |
#           v
#   Notebook 2 - Fraud Intelligence Engine
#           |
#           v
#   Notebook 3 - Decision Intelligence Engine
# 
# Computer vision approach:
# The official PS6 statement asks for "Computer Vision AI", not "a trained
# CNN". This notebook deliberately uses classical, deterministic image
# processing (blur/edge/contrast analysis, region-based feature scoring,
# OCR for serial numbers and denomination numerals) rather than a trained
# neural network: it needs no training dataset to run end-to-end in a
# hackathon timeframe, every decision is directly explainable in terms of
# a measurable image property, and a real trained detector can be dropped
# into Module 6 later without touching any other module - the interface
# (region -> presence/absence/confidence/score) stays the same either way.
# 
# Revision 2 additions:
#   1. Security Feature Confidence  - every feature now carries a
#      confidence percentage and an earned/max weighted score, not just a
#      Present/Missing/Unclear label.
#   2. Region Images                - a cropped image is saved for every
#      inspected region, so a dashboard can show exactly what the AI looked at.
#   3. Confidence Heatmap           - a green/yellow/red overlay of the
#      whole note, in addition to the labeled-box annotation.
#   4. Serial Number Intelligence   - adds OCR confidence and a combined
#      serial-confidence score alongside pattern validity and duplicate checks.
#   5. Feature Dependency Graph     - fine-print features (thread,
#      watermark, microprint) and surface-print features (portrait, seal,
#      signature) are modeled as two clusters; a cluster-level mismatch is
#      itself evidence, not just a per-feature miss.
#   6. Image Authenticity           - coarse EXIF-based check for whether
#      the image looks like a camera photo, a screenshot, or an edited file.
#   7. Image Quality Score          - a numeric 0-100 score alongside the
#      Poor/Acceptable/Excellent label.
#   8. Pipeline Stage Log           - records what happened at every stage
#      (Input -> Quality Check -> Localized -> Rotated -> Denomination ->
#      Features -> Consistency -> Risk) for dashboard display.
#   9. Restructured Package         - grouped into currency_analysis,
#      visual_features, feature_images, risk, audit, and visualization,
#      instead of one flat dict.
#  10. Counterfeit Pattern ID       - assigns a CT-### pattern ID and
#      checks the missing-feature signature against known patterns.
# 
# Architecture fix - decoupling denomination from feature analysis:
# Denomination is now determined ONCE, from (a) the note's aspect ratio,
# (b) its dominant color, and (c) an OCR read of the printed denomination
# numeral - and then LOCKED for the rest of the pipeline. Two changes make
# this robust against being skewed by counterfeit indicators:
#   - Note localization (Module 3) now segments the note from its
#     background using COLOR DISTANCE from the frame's background, not
#     local edge/texture energy. A counterfeit note missing its security
#     thread or watermark is not "less textured" from a background
#     segmentation point of view, so a blank security feature can no
#     longer shrink or skew the detected note boundary - and therefore
#     cannot skew the aspect-ratio-based denomination estimate.
#   - Once detect_denomination() returns a value, no later module
#     recomputes or overrides it. Feature analysis, risk scoring, and
#     explanation all read the same locked denomination.


import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageOps

try:
    import pytesseract
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("counterfeit_currency_intelligence_engine")

# ## 1. Configuration


class Config:
    '''Central configuration for Notebook 5.'''

    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}

    NOTEBOOK_VERSION = "v2.0"

    # --- Module 2: Image Quality thresholds ---
    BLUR_VARIANCE_THRESHOLD_LOW = 40.0      # below this: likely too blurry
    BLUR_VARIANCE_THRESHOLD_MEDIUM = 120.0
    MIN_RESOLUTION_PIXELS = 300 * 150       # width * height floor
    DARK_MEAN_THRESHOLD = 40                # 0-255 scale
    BRIGHT_MEAN_THRESHOLD = 235

    # --- Module 3: Background segmentation ---
    BACKGROUND_PATCH_FRACTION = 0.05        # corner patch size used to sample background color
    BACKGROUND_MIN_FOREGROUND_FRACTION = 0.05  # below this, treat as "no background to remove"

    # --- Module 5: Denomination reference dimensions (mm, RBI Mahatma
    # Gandhi New Series), stored as width:height ratio for aspect-based
    # matching regardless of the uploaded image's pixel resolution. ---
    DENOMINATION_DIMENSIONS_MM: Dict[str, Tuple[float, float]] = {
        "10": (123.0, 63.0),
        "20": (129.0, 63.0),
        "50": (135.0, 66.0),
        "100": (142.0, 66.0),
        "200": (146.0, 66.0),
        "500": (150.0, 66.0),
        "2000": (166.0, 66.0),
    }

    # Approximate dominant note color per denomination (RGB), used as a
    # secondary signal alongside aspect ratio. These are coarse references,
    # not exact print specifications.
    DENOMINATION_DOMINANT_COLOR: Dict[str, Tuple[int, int, int]] = {
        "10": (140, 100, 70),      # chocolate brown
        "20": (200, 190, 90),      # greenish yellow
        "50": (120, 170, 210),     # fluorescent blue
        "100": (170, 150, 190),    # lavender
        "200": (220, 140, 60),     # bright orange
        "500": (150, 145, 135),    # stone grey
        "2000": (170, 90, 140),    # magenta
    }

    # --- Module 9: Risk scoring weights (must sum to 100) ---
    FEATURE_WEIGHTS: Dict[str, int] = {
        "security_thread": 18,
        "watermark": 15,
        "portrait": 12,
        "ashoka_pillar": 8,
        "rbi_seal": 8,
        "governor_signature": 7,
        "microprint": 12,
        "serial_number": 20,
    }

    RISK_LOW_MAX = 25       # score-loss <= this => Low risk
    RISK_MEDIUM_MAX = 50    # score-loss <= this => Medium risk
    # anything above RISK_MEDIUM_MAX => High risk


CONFIG = Config()
assert sum(CONFIG.FEATURE_WEIGHTS.values()) == 100, "Feature weights must sum to 100."
logger.info("Notebook 5 configuration loaded. version=%s", CONFIG.NOTEBOOK_VERSION)

# ## 2. Core Enums


class ImageQuality(str, Enum):
    POOR = "Poor"
    ACCEPTABLE = "Acceptable"
    EXCELLENT = "Excellent"


class FeatureStatus(str, Enum):
    PRESENT = "Present"
    MISSING = "Missing"
    UNCLEAR = "Unclear"


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class CounterfeitIntelligenceError(Exception):
    '''Raised when Notebook 5 cannot produce a valid currency intelligence package.'''

# ## 3. Module 1 - Currency Intake


def ingest_currency_image(file_path: str) -> str:
    '''Module 1 entry point. Validates the file exists and is a supported format.'''
    if not os.path.exists(file_path):
        raise CounterfeitIntelligenceError(f"File not found: {file_path}")
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in CONFIG.SUPPORTED_EXTENSIONS:
        raise CounterfeitIntelligenceError(
            f"Unsupported currency image format {ext!r}; supported: {sorted(CONFIG.SUPPORTED_EXTENSIONS)}"
        )
    logger.info("Ingested currency image. path=%s", file_path)
    return file_path

# ## 4. Module 2 - Image Quality Assessment (+ numeric Quality Score, feature 7)


@dataclass
class QualityReport:
    quality: str                # ImageQuality value
    quality_score: float        # 0-100 numeric score
    blur_variance: float
    mean_brightness: float
    resolution: Tuple[int, int]
    issues: List[str] = field(default_factory=list)


def _laplacian_variance(gray: np.ndarray) -> float:
    '''
    Classical blur metric: convolve with a Laplacian kernel and take the
    variance of the response. Sharp images have high-variance edges;
    blurry images have low-variance, smoothed-out edges. No external CV
    library needed - implemented directly with numpy.
    '''
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    padded = np.pad(gray, 1, mode="edge").astype(np.float32)
    response = (
        padded[0:-2, 1:-1] * kernel[0, 1]
        + padded[1:-1, 0:-2] * kernel[1, 0]
        + padded[1:-1, 1:-1] * kernel[1, 1]
        + padded[1:-1, 2:] * kernel[1, 2]
        + padded[2:, 1:-1] * kernel[2, 1]
    )
    return float(response.var())


def _compute_quality_score(blur_variance: float, mean_brightness: float, width: int, height: int) -> float:
    '''New (feature 7): folds blur, brightness, and resolution into one 0-100 score.'''
    blur_component = min(1.0, blur_variance / CONFIG.BLUR_VARIANCE_THRESHOLD_MEDIUM) * 50
    ideal_brightness = 127.5
    brightness_component = max(0.0, 1 - abs(mean_brightness - ideal_brightness) / ideal_brightness) * 30
    resolution_component = min(1.0, (width * height) / (CONFIG.MIN_RESOLUTION_PIXELS * 4)) * 20
    return round(blur_component + brightness_component + resolution_component, 1)


def assess_image_quality(image: Image.Image) -> QualityReport:
    '''Module 2 entry point.'''
    gray = np.array(ImageOps.grayscale(image), dtype=np.float32)
    blur_variance = _laplacian_variance(gray)
    mean_brightness = float(gray.mean())
    width, height = image.size
    quality_score = _compute_quality_score(blur_variance, mean_brightness, width, height)

    issues: List[str] = []
    if blur_variance < CONFIG.BLUR_VARIANCE_THRESHOLD_LOW:
        issues.append("Image appears blurry; edges are too soft for reliable feature detection.")
    if width * height < CONFIG.MIN_RESOLUTION_PIXELS:
        issues.append(f"Resolution ({width}x{height}) is below the recommended minimum.")
    if mean_brightness < CONFIG.DARK_MEAN_THRESHOLD:
        issues.append("Image is too dark; recapture with better lighting.")
    if mean_brightness > CONFIG.BRIGHT_MEAN_THRESHOLD:
        issues.append("Image is overexposed; reduce glare or flash reflection.")

    if issues:
        quality = ImageQuality.POOR.value if len(issues) >= 2 or blur_variance < CONFIG.BLUR_VARIANCE_THRESHOLD_LOW else ImageQuality.ACCEPTABLE.value
    elif blur_variance >= CONFIG.BLUR_VARIANCE_THRESHOLD_MEDIUM:
        quality = ImageQuality.EXCELLENT.value
    else:
        quality = ImageQuality.ACCEPTABLE.value

    report = QualityReport(
        quality=quality, quality_score=quality_score, blur_variance=round(blur_variance, 1),
        mean_brightness=round(mean_brightness, 1), resolution=(width, height), issues=issues,
    )
    logger.info("Image quality assessed. quality=%s score=%.1f blur_variance=%.1f brightness=%.1f",
                report.quality, quality_score, blur_variance, mean_brightness)
    return report

# ## 5. Module 3 - Note Localization (background-color segmentation)


def _estimate_background_color(image: Image.Image) -> np.ndarray:
    '''Samples the four corner patches and averages them as the background estimate.'''
    arr = np.array(image.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    ph = max(1, int(h * CONFIG.BACKGROUND_PATCH_FRACTION))
    pw = max(1, int(w * CONFIG.BACKGROUND_PATCH_FRACTION))
    corners = [arr[0:ph, 0:pw], arr[0:ph, w - pw:w], arr[h - ph:h, 0:pw], arr[h - ph:h, w - pw:w]]
    stacked = np.concatenate([c.reshape(-1, 3) for c in corners], axis=0)
    return stacked.mean(axis=0)


def localize_note(image: Image.Image) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    '''
    Module 3 entry point.

    Segments the note from its background using COLOR DISTANCE from an
    estimated background color (sampled from the four image corners),
    rather than local edge/texture energy. This is the fix for the
    denomination-skew issue: a security feature that is faint, blurred, or
    entirely missing does not change how different the note's surface is
    from the background behind it, so it cannot shrink or distort the
    detected note boundary the way an edge/texture-based method could.
    If no clear background-to-foreground boundary is found (e.g. the note
    already fills the frame), the original image is used unchanged.
    '''
    arr = np.array(image.convert("RGB"), dtype=np.float32)
    background = _estimate_background_color(image)
    distance = np.linalg.norm(arr - background, axis=2)

    threshold = max(15.0, float(distance.std()) * 1.2)
    mask = distance > threshold
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]

    total_pixels = arr.shape[0] * arr.shape[1]
    foreground_pixels = int(mask.sum())

    if len(rows) == 0 or len(cols) == 0 or foreground_pixels < CONFIG.BACKGROUND_MIN_FOREGROUND_FRACTION * total_pixels:
        logger.info("No clear background-to-note boundary found; using full image as the note region.")
        return image, (0, 0, image.width, image.height)

    top, bottom = int(rows[0]), int(rows[-1])
    left, right = int(cols[0]), int(cols[-1])

    pad_x = max(2, int(0.02 * (right - left)))
    pad_y = max(2, int(0.02 * (bottom - top)))
    left = max(0, left - pad_x)
    top = max(0, top - pad_y)
    right = min(image.width, right + pad_x)
    bottom = min(image.height, bottom + pad_y)

    cropped = image.crop((left, top, right, bottom))
    logger.info("Note localized via background segmentation. bounding_box=%s", (left, top, right, bottom))
    return cropped, (left, top, right, bottom)

# ## 6. Module 4 - Orientation Correction


def correct_orientation(image: Image.Image) -> Tuple[Image.Image, bool]:
    '''
    Module 4 entry point.

    RBI notes are landscape (wider than tall). If the uploaded crop is
    portrait, rotate it 90 degrees. This notebook does not attempt to
    detect a 180-degree (upside-down) flip automatically, since that
    requires recognizing the portrait's actual orientation - it flags this
    as a known limitation rather than guessing.
    '''
    width, height = image.size
    if height > width:
        rotated = image.rotate(-90, expand=True)
        logger.info("Note was portrait-oriented; rotated 90 degrees to landscape.")
        return rotated, True
    return image, False

# ## 7. Feature Regions (shared by Modules 5, 6, 7, 13, and the heatmap/crops)
# 
# (left_frac, top_frac, right_frac, bottom_frac) as fractions of the
# localized, landscape-oriented note image. Regions are deliberately kept
# non-overlapping so texture belonging to one feature (e.g. the portrait)
# cannot be mistaken for another (e.g. the security thread) during scoring.


_FEATURE_REGIONS: Dict[str, Tuple[float, float, float, float]] = {
    "watermark": (0.02, 0.10, 0.15, 0.90),
    "security_thread": (0.17, 0.05, 0.23, 0.95),
    "microprint": (0.25, 0.55, 0.32, 0.68),
    "portrait": (0.34, 0.15, 0.64, 0.88),
    "governor_signature": (0.34, 0.90, 0.64, 0.97),
    "rbi_seal": (0.66, 0.60, 0.80, 0.85),
    "ashoka_pillar": (0.90, 0.10, 0.99, 0.60),
    "serial_number_top_left": (0.03, 0.03, 0.15, 0.09),
    "serial_number_bottom_right": (0.80, 0.88, 0.98, 0.97),
}

# Approximate location of the printed denomination numeral, used only for
# the OCR cross-check in Module 5 - not part of the security-feature scoring
# loop, so it does not affect texture-based Present/Missing/Unclear scoring.
_DENOMINATION_NUMERAL_REGION: Tuple[float, float, float, float] = (0.82, 0.02, 0.99, 0.16)


def _region_box_pixels(image: Image.Image, frac_box: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    width, height = image.size
    l, t, r, b = frac_box
    return (int(l * width), int(t * height), int(r * width), int(b * height))


def _region_pixels(image: Image.Image, frac_box: Tuple[float, float, float, float]) -> np.ndarray:
    region = image.crop(_region_box_pixels(image, frac_box))
    return np.array(ImageOps.grayscale(region), dtype=np.float32)

# ## 8. Module 5 - Denomination Detection (locked once, never recomputed)


@dataclass
class DenominationResult:
    denomination: str
    confidence: float
    matched_by: List[str]


def _aspect_ratio_scores(width: int, height: int) -> Dict[str, float]:
    observed_ratio = width / height if height else 0
    scores: Dict[str, float] = {}
    for denom, (mm_w, mm_h) in CONFIG.DENOMINATION_DIMENSIONS_MM.items():
        expected_ratio = mm_w / mm_h
        diff = abs(observed_ratio - expected_ratio)
        scores[denom] = max(0.0, 1.0 - diff / expected_ratio)
    return scores


def _color_scores(image: Image.Image) -> Dict[str, float]:
    small = image.resize((32, 32))
    arr = np.array(small.convert("RGB"), dtype=np.float32).reshape(-1, 3)
    dominant = arr.mean(axis=0)
    scores: Dict[str, float] = {}
    for denom, color in CONFIG.DENOMINATION_DOMINANT_COLOR.items():
        distance = float(np.linalg.norm(dominant - np.array(color, dtype=np.float32)))
        max_distance = float(np.linalg.norm(np.array([255, 255, 255])))
        scores[denom] = max(0.0, 1.0 - distance / max_distance)
    return scores


def _ocr_denomination_numeral(image: Image.Image) -> Optional[str]:
    '''OCR cross-check: reads the printed denomination numeral directly, when legible.'''
    if not _TESSERACT_AVAILABLE:
        return None
    box = _region_box_pixels(image, _DENOMINATION_NUMERAL_REGION)
    region = image.crop(box)
    if region.width == 0 or region.height == 0:
        return None
    region = region.resize((max(1, region.width * 3), max(1, region.height * 3)))
    try:
        text = pytesseract.image_to_string(region, config="--psm 7 -c tessedit_char_whitelist=0123456789")
    except Exception as exc:
        logger.warning("Denomination numeral OCR failed: %s", exc)
        return None
    digits = re.sub(r"[^0-9]", "", text)
    return digits if digits in CONFIG.DENOMINATION_DIMENSIONS_MM else None


def detect_denomination(image: Image.Image, hint: Optional[str] = None) -> DenominationResult:
    '''
    Module 5 entry point. Called exactly once per analysis, on the
    localized + oriented note image, before any feature-region texture
    analysis runs. Its return value is treated as LOCKED: no other module
    in this file recomputes or overrides it.

    Signal priority: an explicit citizen-confirmed hint wins outright;
    otherwise a legible OCR read of the printed numeral is trusted over
    the aspect-ratio/color heuristic (reading the actual printed number is
    stronger ground truth than inferring it from shape and color); with no
    OCR read, aspect ratio (strong) and dominant color (weak) combine.
    '''
    if hint and hint in CONFIG.DENOMINATION_DIMENSIONS_MM:
        return DenominationResult(denomination=f"Rs {hint}", confidence=99.0, matched_by=["user_supplied_hint"])

    width, height = image.size
    ratio_scores = _aspect_ratio_scores(width, height)
    color_scores = _color_scores(image)

    combined = {
        denom: 0.7 * ratio_scores.get(denom, 0) + 0.3 * color_scores.get(denom, 0)
        for denom in CONFIG.DENOMINATION_DIMENSIONS_MM
    }
    best_denom = max(combined, key=combined.get)
    confidence = round(combined[best_denom] * 100, 1)
    matched_by = ["aspect_ratio"]
    if color_scores.get(best_denom, 0) > 0.6:
        matched_by.append("dominant_color")

    ocr_numeral = _ocr_denomination_numeral(image)
    if ocr_numeral:
        if ocr_numeral == best_denom:
            matched_by.append("ocr_numeral_confirmation")
            confidence = min(99.9, confidence + 15)
        else:
            logger.info(
                "OCR numeral (%s) disagreed with the aspect-ratio/color estimate (%s); trusting the OCR read.",
                ocr_numeral, best_denom,
            )
            best_denom = ocr_numeral
            confidence = 95.0
            matched_by = ["ocr_numeral"]

    result = DenominationResult(denomination=f"Rs {best_denom}", confidence=round(confidence, 1), matched_by=matched_by)
    logger.info("Denomination locked. denomination=%s confidence=%.1f matched_by=%s",
                result.denomination, result.confidence, matched_by)
    return result

# ## 9. Module 6 - Security Feature Detection
# 
# Each RBI note has a fixed layout: the security thread runs vertically
# left-of-center, the watermark sits in the blank left margin, the
# portrait dominates the center-right, the Ashoka pillar sits at the far
# right, and so on. Because the note has already been localized and
# oriented (Modules 3-4), these regions can be addressed as fixed
# proportions of the cropped image regardless of its pixel resolution.
# 
# Each region is scored by local texture/contrast (standard deviation of
# pixel intensity): a blank, poorly-printed, or missing security feature
# reads as low local variance; genuine fine print reads as higher local
# variance. This is a proxy signal, not a certified authenticity check -
# Module 10's explanation is careful to say so.


_PRESENT_VARIANCE_THRESHOLD = 12.0
_UNCLEAR_VARIANCE_THRESHOLD = 5.0

_SCORED_FEATURES = ("security_thread", "watermark", "portrait", "ashoka_pillar",
                     "rbi_seal", "governor_signature", "microprint")


def detect_security_features(image: Image.Image, quality: QualityReport) -> Dict[str, Dict[str, Any]]:
    '''Module 6 entry point. Returns per-feature status, confidence, and raw texture score.'''
    results: Dict[str, Dict[str, Any]] = {}

    for feature in _SCORED_FEATURES:
        pixels = _region_pixels(image, _FEATURE_REGIONS[feature])
        texture = float(pixels.std()) if pixels.size else 0.0

        if quality.quality == ImageQuality.POOR.value:
            status = FeatureStatus.UNCLEAR.value
            confidence = 40.0
        elif texture >= _PRESENT_VARIANCE_THRESHOLD:
            status = FeatureStatus.PRESENT.value
            confidence = min(99.0, 60.0 + texture)
        elif texture >= _UNCLEAR_VARIANCE_THRESHOLD:
            status = FeatureStatus.UNCLEAR.value
            confidence = 50.0
        else:
            status = FeatureStatus.MISSING.value
            confidence = max(10.0, 60.0 - texture * 4)

        results[feature] = {"status": status, "confidence": round(confidence, 1), "texture_score": round(texture, 2)}

    logger.info("Security features detected. %s", {k: v["status"] for k, v in results.items()})
    return results

# ## 10. Module 5b - Region Images (feature 2)


def save_feature_crops(image: Image.Image, output_dir: str) -> Dict[str, str]:
    '''
    New (feature 2): saves a cropped image for every inspected region
    (including both serial-number regions) so a dashboard can display
    exactly what area of the note the AI examined for each feature.
    '''
    os.makedirs(output_dir, exist_ok=True)
    paths: Dict[str, str] = {}
    for region_name, frac_box in _FEATURE_REGIONS.items():
        crop = image.crop(_region_box_pixels(image, frac_box))
        crop_path = os.path.join(output_dir, f"crop_{region_name}.png")
        crop.save(crop_path)
        paths[region_name] = crop_path
    return paths

# ## 11. Module 7 - Serial Number Intelligence (+ OCR/serial confidence, feature 4)
# 
# RBI serial numbers follow a family of formats over the years but a very
# common current pattern is: two letters, a numeral (the note series
# indicator), then a 6-digit running number, e.g. "3AK 123456". This
# pattern intentionally stays loose (it validates shape, not authenticity)
# because format alone cannot confirm genuineness - it can only flag an
# obviously malformed serial for follow-up.


_SERIAL_PATTERN = re.compile(r"\b[0-9]?[A-Z]{2}\s?\d{6}\b")


def _ocr_confidence_for_region(image: Image.Image, frac_box: Tuple[float, float, float, float]) -> Tuple[str, float]:
    '''Runs OCR with per-word confidence and returns (joined_text, average_confidence).'''
    box = _region_box_pixels(image, frac_box)
    region = image.crop(box)
    region = region.resize((max(1, region.width * 3), max(1, region.height * 3)))
    try:
        data = pytesseract.image_to_data(
            region, output_type=pytesseract.Output.DICT,
            config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
    except Exception as exc:
        logger.warning("Serial OCR confidence read failed: %s", exc)
        return "", 0.0

    words = [w for w in data.get("text", []) if w.strip()]
    confidences = [c for c in data.get("conf", []) if isinstance(c, (int, float)) and c >= 0]
    text = " ".join(words)
    avg_conf = float(np.mean(confidences)) if confidences else 0.0
    return text, avg_conf


def extract_serial_number(image: Image.Image, known_serial_database: Optional[List[str]] = None) -> Dict[str, Any]:
    '''Module 7 entry point.'''
    if not _TESSERACT_AVAILABLE:
        return {
            "serial_number": None, "format_valid": None, "ocr_confidence": None,
            "serial_confidence": None, "duplicate_flagged": None,
            "notes": ["pytesseract not available; serial number was not read."],
        }

    candidates: List[Tuple[str, float]] = []
    for region_name in ("serial_number_top_left", "serial_number_bottom_right"):
        text, ocr_conf = _ocr_confidence_for_region(image, _FEATURE_REGIONS[region_name])
        match = _SERIAL_PATTERN.search(text.upper())
        if match:
            candidates.append((match.group(0).replace(" ", ""), ocr_conf))

    if not candidates:
        return {
            "serial_number": None, "format_valid": None, "ocr_confidence": None,
            "serial_confidence": None, "duplicate_flagged": None,
            "notes": ["No serial number could be read from the expected regions."],
        }

    # Prefer the read with higher OCR confidence if the two regions disagree.
    candidates.sort(key=lambda c: c[1], reverse=True)
    serial, ocr_conf = candidates[0]
    format_valid = True
    duplicate_flagged = bool(known_serial_database and serial in known_serial_database)

    # New (feature 4): combined serial confidence blends format validity
    # (binary, but informative) with OCR read confidence.
    format_component = 100.0 if format_valid else 0.0
    serial_confidence = round(0.5 * format_component + 0.5 * ocr_conf, 1)

    notes = []
    if duplicate_flagged:
        notes.append("This serial number already exists in the known-case database.")

    return {
        "serial_number": serial,
        "format_valid": format_valid,
        "ocr_confidence": round(ocr_conf, 1),
        "serial_confidence": serial_confidence,
        "duplicate_flagged": duplicate_flagged,
        "notes": notes,
    }

# ## 12. Module 8 - Feature Consistency Analysis & Dependency Graph (feature 5)
# 
# A genuine note's features tend to move together: if the image is sharp
# enough to show a crisp portrait, it should also be sharp enough to show
# the microprint. Fine-detail features (thread, watermark, microprint) and
# surface-print features (portrait, seal, signature) are modeled as two
# dependency clusters; a mismatch between clusters is itself a signal,
# independent of any single feature's raw score.


_FEATURE_DEPENDENCY_GROUPS: Dict[str, List[str]] = {
    "fine_print_cluster": ["security_thread", "watermark", "microprint"],
    "surface_print_cluster": ["portrait", "rbi_seal", "governor_signature"],
}


def build_feature_dependency_graph(security_features: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    '''New (feature 5): reports each cluster's internal agreement and flags cross-cluster conflict.'''
    clusters = []
    for group_name, members in _FEATURE_DEPENDENCY_GROUPS.items():
        statuses = {m: security_features[m]["status"] for m in members}
        present_count = list(statuses.values()).count(FeatureStatus.PRESENT.value)
        missing_count = list(statuses.values()).count(FeatureStatus.MISSING.value)
        if present_count == len(members) or missing_count == len(members):
            cluster_status = "Consistent"
        else:
            cluster_status = "Partially Present"
        clusters.append({"cluster": group_name, "members": members, "statuses": statuses, "cluster_status": cluster_status})

    surface_present = sum(
        1 for m in _FEATURE_DEPENDENCY_GROUPS["surface_print_cluster"]
        if security_features[m]["status"] == FeatureStatus.PRESENT.value
    )
    fine_missing = sum(
        1 for m in _FEATURE_DEPENDENCY_GROUPS["fine_print_cluster"]
        if security_features[m]["status"] == FeatureStatus.MISSING.value
    )
    cross_cluster_conflict = surface_present >= 2 and fine_missing >= 2

    return {"clusters": clusters, "cross_cluster_conflict": cross_cluster_conflict}


def analyze_feature_consistency(security_features: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    '''Module 8 entry point. Built on top of the dependency graph above.'''
    graph = build_feature_dependency_graph(security_features)
    inconsistent = graph["cross_cluster_conflict"]

    if inconsistent:
        notes = [
            "Image sharpness is sufficient to render the portrait and seal clearly, "
            "yet fine-detail security features (thread, watermark, microprint) are missing. "
            "This pattern is inconsistent with a genuine note and image-quality alone."
        ]
    else:
        notes = ["No sharpness-inconsistent feature pattern detected."]

    return {"inconsistent_pattern_detected": inconsistent, "notes": notes, "dependency_graph": graph}

# ## 13. Module 9 - Counterfeit Risk Engine (+ per-feature score, feature 1)


def calculate_counterfeit_risk(
    security_features: Dict[str, Dict[str, Any]],
    serial_result: Dict[str, Any],
    consistency: Dict[str, Any],
) -> Dict[str, Any]:
    '''
    Module 9 entry point. Combines all feature scores into one risk
    verdict, and (feature 1) writes the earned/max weighted score back
    into each feature's own record so downstream consumers see confidence
    AND score together, not confidence alone.
    '''
    score = 0.0
    feature_breakdown: Dict[str, Dict[str, float]] = {}

    for feature, weight in CONFIG.FEATURE_WEIGHTS.items():
        if feature == "serial_number":
            if serial_result.get("format_valid") is True and not serial_result.get("duplicate_flagged"):
                earned = weight
            elif serial_result.get("format_valid") is None:
                earned = weight * 0.5   # unverifiable, not penalized as if missing
            else:
                earned = 0.0
        else:
            status = security_features[feature]["status"]
            if status == FeatureStatus.PRESENT.value:
                earned = weight
            elif status == FeatureStatus.UNCLEAR.value:
                earned = weight * 0.5
            else:
                earned = 0.0
            # Feature 1: attach the earned/max score directly onto the
            # feature's own record, alongside its status and confidence.
            security_features[feature]["score"] = round(earned, 1)
            security_features[feature]["max_score"] = weight

        feature_breakdown[feature] = {"earned": round(earned, 1), "max": weight}
        score += earned

    if consistency["inconsistent_pattern_detected"]:
        score = max(0.0, score - 10)  # additional penalty for the inconsistency pattern itself

    score_loss = 100 - score
    if score_loss <= CONFIG.RISK_LOW_MAX:
        risk = RiskLevel.LOW.value
    elif score_loss <= CONFIG.RISK_MEDIUM_MAX:
        risk = RiskLevel.MEDIUM.value
    else:
        risk = RiskLevel.HIGH.value

    genuine_probability = round(score / 100, 2)
    counterfeit_probability = round(1 - genuine_probability, 2)

    result = {
        "score": round(score, 1),
        "genuine_probability": genuine_probability,
        "counterfeit_probability": counterfeit_probability,
        "risk": risk,
        "feature_breakdown": feature_breakdown,
    }
    logger.info("Counterfeit risk calculated. score=%.1f risk=%s", score, risk)
    return result

# ## 14. Module 10 - Explainable AI


_FEATURE_LABELS: Dict[str, str] = {
    "security_thread": "Security thread",
    "watermark": "Watermark",
    "portrait": "Mahatma Gandhi portrait",
    "ashoka_pillar": "Ashoka Pillar emblem",
    "rbi_seal": "RBI seal",
    "governor_signature": "Governor's signature area",
    "microprint": "Microprint region",
}


def generate_explanation(
    security_features: Dict[str, Dict[str, Any]],
    serial_result: Dict[str, Any],
    consistency: Dict[str, Any],
    risk_result: Dict[str, Any],
) -> List[str]:
    '''Module 10 entry point. Plain-language reasoning, not a bare verdict.'''
    explanation: List[str] = []

    for feature, label in _FEATURE_LABELS.items():
        status = security_features[feature]["status"]
        confidence = security_features[feature]["confidence"]
        if status == FeatureStatus.PRESENT.value:
            explanation.append(f"{label} detected in the expected location ({confidence}% confidence).")
        elif status == FeatureStatus.UNCLEAR.value:
            explanation.append(f"{label} could not be clearly verified, likely due to image resolution or angle.")
        else:
            explanation.append(f"{label} was not detected in the expected location.")

    if serial_result.get("serial_number"):
        explanation.append(
            f"Serial number read as {serial_result['serial_number']} "
            f"(serial confidence {serial_result.get('serial_confidence')}%)."
        )
        if serial_result.get("duplicate_flagged"):
            explanation.append("This serial number matches a previously reported note.")
    else:
        explanation.append("Serial number could not be read from the image.")

    explanation.extend(consistency["notes"] if consistency["inconsistent_pattern_detected"] else [])

    explanation.append(
        f"Overall feature score: {risk_result['score']}/100 -> {risk_result['risk']} counterfeit risk."
    )
    return explanation

# ## 15. Module 11 - RBI Knowledge Retrieval
# 
# In the full platform this queries Notebook 1's knowledge base (the same
# vector store used by Notebook 2) for the official RBI security-feature
# description of the detected denomination, so the explanation can say
# "According to RBI, Rs 500 notes should contain..." instead of a bare
# feature list. Notebook 5 has no vector store dependency of its own, so
# this module is a thin, swappable lookup - the static table below stands
# in for that retrieval call, and is intentionally organized so it can be
# replaced by a real `notebook1_query(denomination)` call without changing
# any other module.


_RBI_FEATURE_REFERENCE: Dict[str, str] = {
    "10": "The Rs 10 note (Mahatma Gandhi New Series) features a Konark Sun Temple motif, "
          "a windowed security thread, and a see-through register with the numeral 10.",
    "20": "The Rs 20 note features an Ellora Caves motif, a windowed security thread, "
          "and a latent image showing the denomination.",
    "50": "The Rs 50 note features a Hampi with Chariot motif, a windowed security thread, "
          "and fluorescent-blue base color with a see-through register.",
    "100": "The Rs 100 note features a Rani ki Vav motif, a windowed security thread inscribed "
           "'RBI' and 'Bharat', and a lavender base color.",
    "200": "The Rs 200 note features a Sanchi Stupa motif, a windowed security thread, "
           "and a bright orange base color with the numeral 200 in the watermark.",
    "500": "The Rs 500 note features a Red Fort motif, a windowed security thread inscribed "
           "'RBI' and 'Bharat', a stone-grey base color, and a see-through register with 500.",
    "2000": "The Rs 2000 note features a Mangalyaan motif, a windowed security thread, "
            "and a magenta base color with the numeral 2000 in the watermark.",
}


def retrieve_rbi_reference(denomination: str) -> str:
    '''Module 11 entry point.'''
    denom_number = denomination.replace("Rs", "").strip()
    return _RBI_FEATURE_REFERENCE.get(
        denom_number,
        f"No official RBI feature reference is on file for denomination {denomination!r}.",
    )

# ## 16. Module 12b - Image Authenticity (feature 6)


def assess_image_authenticity(image: Image.Image) -> Dict[str, Any]:
    '''
    New (feature 6): coarse EXIF-based check for whether the image looks
    like a direct camera photo, a screenshot, or an edited file. This is a
    weak, easily-spoofed supporting signal (metadata can be stripped or
    forged) - it is reported as a hint for the investigator, never as
    proof, and never feeds into the counterfeit risk score itself.
    '''
    try:
        exif = image.getexif()
    except Exception:
        exif = None

    has_exif = bool(exif and len(exif) > 0)
    make = exif.get(271) if exif else None       # EXIF tag 271 = Make
    model = exif.get(272) if exif else None       # EXIF tag 272 = Model
    software = exif.get(305) if exif else None    # EXIF tag 305 = Software

    indicators: List[str] = []
    likely_source = "Unknown"

    if not has_exif:
        likely_source = "Screenshot or Edited Image (no EXIF metadata found)"
        indicators.append("No EXIF metadata present; genuine camera photos typically retain camera metadata.")
    elif make or model:
        likely_source = "Camera Photo"
        indicators.append(f"EXIF camera metadata found (Make={make!r}, Model={model!r}).")

    if software and any(tag in str(software).lower() for tag in ("photoshop", "gimp", "snapseed", "lightroom", "pixelmator")):
        likely_source = "Edited Image"
        indicators.append(f"EXIF Software tag indicates image-editing software was used: {software!r}.")

    if not indicators:
        indicators.append("Insufficient metadata to determine image source with confidence.")

    return {"likely_source": likely_source, "has_exif": has_exif, "indicators": indicators}

# ## 17. Module 13 - Visualization (annotated boxes + confidence heatmap, feature 3)


_STATUS_MARKS = {
    FeatureStatus.PRESENT.value: "OK",
    FeatureStatus.MISSING.value: "MISSING",
    FeatureStatus.UNCLEAR.value: "UNCLEAR",
}
_STATUS_COLORS = {
    FeatureStatus.PRESENT.value: (0, 170, 0),
    FeatureStatus.MISSING.value: (200, 0, 0),
    FeatureStatus.UNCLEAR.value: (200, 150, 0),
}


def build_annotated_image(image: Image.Image, security_features: Dict[str, Dict[str, Any]], output_path: str) -> str:
    '''Module 13 entry point (labeled boxes). Draws each checked region with its status label.'''
    annotated = image.convert("RGB").copy()
    draw = ImageDraw.Draw(annotated)

    for feature, result in security_features.items():
        if feature not in _FEATURE_REGIONS:
            continue
        box = _region_box_pixels(annotated, _FEATURE_REGIONS[feature])
        color = _STATUS_COLORS[result["status"]]
        draw.rectangle(box, outline=color, width=2)
        label = f"{feature}: {_STATUS_MARKS[result['status']]}"
        draw.text((box[0] + 2, max(0, box[1] - 12)), label, fill=color)

    annotated.save(output_path)
    logger.info("Annotated visualization saved to %s", output_path)
    return output_path


def build_confidence_heatmap(image: Image.Image, security_features: Dict[str, Dict[str, Any]], output_path: str) -> str:
    '''
    New (feature 3): a green/yellow/red translucent overlay across the
    whole note - green where a feature verified, yellow where unclear, red
    where missing - so the overall picture reads at a glance, distinct
    from the labeled-box annotation above.
    '''
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for feature, result in security_features.items():
        if feature not in _FEATURE_REGIONS:
            continue
        box = _region_box_pixels(base, _FEATURE_REGIONS[feature])
        color = _STATUS_COLORS[result["status"]] + (110,)  # semi-transparent fill
        draw.rectangle(box, fill=color)

    heatmap = Image.alpha_composite(base, overlay).convert("RGB")
    heatmap.save(output_path)
    logger.info("Confidence heatmap saved to %s", output_path)
    return output_path

# ## 18. Module 14 - Audit Log


def build_audit_log(
    image_path: str,
    features_checked: List[str],
    risk_result: Dict[str, Any],
) -> Dict[str, Any]:
    '''Module 14 entry point.'''
    with open(image_path, "rb") as fh:
        image_hash = hashlib.sha256(fh.read()).hexdigest()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image_hash": image_hash,
        "features_checked": features_checked,
        "decision": risk_result["risk"],
        "confidence": round(risk_result["genuine_probability"] * 100, 1),
        "notebook_version": CONFIG.NOTEBOOK_VERSION,
    }

# ## 19. Counterfeit Pattern ID (feature 10)


_pattern_counters: Dict[str, int] = {}   # in-memory demo counter; a real deployment uses a DB sequence

_KNOWN_PATTERN_SIGNATURES: Dict[frozenset, str] = {
    frozenset({"security_thread", "watermark"}): "Photocopy/print fake pattern (thread and watermark both absent).",
    frozenset({"microprint"}): "Low-quality reproduction pattern (microprint absent, other features intact).",
    frozenset({"security_thread", "watermark", "microprint"}): "Full fine-detail fabrication - high-risk counterfeit pattern.",
    frozenset({"ashoka_pillar"}): "Edge-trim or cropped-scan pattern (Ashoka Pillar area absent).",
}


def assign_counterfeit_pattern_id(missing_features: List[str]) -> Dict[str, Any]:
    '''
    New (feature 10): assigns a stable-looking pattern ID (CT-001, CT-002,
    ...) and checks the specific combination of missing features against a
    small table of previously-seen counterfeit patterns.
    '''
    signature = frozenset(f for f in missing_features if f in CONFIG.FEATURE_WEIGHTS and f != "serial_number")
    _pattern_counters["CT"] = _pattern_counters.get("CT", 0) + 1
    pattern_id = f"CT-{_pattern_counters['CT']:03d}"
    known_match = _KNOWN_PATTERN_SIGNATURES.get(signature)
    return {
        "pattern_id": pattern_id,
        "missing_feature_signature": sorted(signature),
        "known_pattern_match": known_match or "No matching known counterfeit pattern on file.",
    }

# ## 20. Module 12 - Counterfeit Intelligence Package (Orchestration)


def analyze_currency_image(
    file_path: str,
    denomination_hint: Optional[str] = None,
    known_serial_database: Optional[List[str]] = None,
    save_visualization: bool = True,
    visualization_dir: str = "/tmp/notebook5_annotated",
    crops_dir: str = "/tmp/notebook5_crops",
) -> Dict[str, Any]:
    '''
    Notebook 5 orchestration - Modules 1-14 combined.

    Runs the full pipeline: intake, quality check, localization,
    orientation correction, denomination locking, security-feature
    detection, serial-number OCR, consistency/dependency analysis, risk
    scoring, explanation generation, RBI reference lookup, image
    authenticity check, visualization, region-crop export, pattern ID
    assignment, and audit logging. Returns the restructured Counterfeit
    Intelligence Package (feature 9) that Notebook 2 merges into its
    broader fraud reasoning.
    '''
    stages: List[Dict[str, str]] = []   # feature 8: pipeline stage log

    try:
        ingest_currency_image(file_path)
        image = Image.open(file_path)
        stages.append({"stage": "Input", "summary": f"Loaded {os.path.basename(file_path)} ({image.size[0]}x{image.size[1]})"})

        quality = assess_image_quality(image)
        stages.append({"stage": "Quality Check", "summary": f"{quality.quality} ({quality.quality_score}/100)"})
        if quality.quality == ImageQuality.POOR.value:
            logger.warning("Image quality is Poor; feature detection will be low-confidence.")

        localized, bounding_box = localize_note(image)
        stages.append({"stage": "Localized", "summary": f"Note bounding box {bounding_box}"})

        oriented, was_rotated = correct_orientation(localized)
        stages.append({"stage": "Rotated", "summary": "Rotated 90 degrees to landscape" if was_rotated else "No rotation needed"})

        # Denomination is determined here, once, and locked for the rest
        # of the pipeline - see the architecture note at the top of this file.
        denomination = detect_denomination(oriented, hint=denomination_hint)
        stages.append({"stage": "Denomination", "summary": f"{denomination.denomination} (confidence {denomination.confidence}%, via {denomination.matched_by})"})

        security_features = detect_security_features(oriented, quality)
        stages.append({"stage": "Features", "summary": f"{sum(1 for f in security_features.values() if f['status']=='Present')}/{len(security_features)} features Present"})

        serial_result = extract_serial_number(oriented, known_serial_database)
        consistency = analyze_feature_consistency(security_features)
        stages.append({"stage": "Consistency", "summary": "Inconsistent pattern detected" if consistency["inconsistent_pattern_detected"] else "Consistent"})

        risk_result = calculate_counterfeit_risk(security_features, serial_result, consistency)
        stages.append({"stage": "Risk", "summary": f"{risk_result['risk']} risk (score {risk_result['score']}/100)"})

        explanation = generate_explanation(security_features, serial_result, consistency, risk_result)

        rbi_reference = retrieve_rbi_reference(denomination.denomination)
        authenticity = assess_image_authenticity(image)
        missing_features = [f for f, r in security_features.items() if r["status"] == FeatureStatus.MISSING.value]
        pattern_info = assign_counterfeit_pattern_id(missing_features)

        visualization = {"annotated_image": None, "confidence_heatmap": None}
        feature_images: Dict[str, str] = {}
        if save_visualization:
            os.makedirs(visualization_dir, exist_ok=True)
            suffix = uuid.uuid4().hex[:8]
            visualization["annotated_image"] = build_annotated_image(
                oriented, security_features, os.path.join(visualization_dir, f"annotated_{suffix}.png")
            )
            visualization["confidence_heatmap"] = build_confidence_heatmap(
                oriented, security_features, os.path.join(visualization_dir, f"heatmap_{suffix}.png")
            )
            feature_images = save_feature_crops(oriented, os.path.join(crops_dir, suffix))

        audit_log = build_audit_log(file_path, list(security_features.keys()) + ["serial_number"], risk_result)

        # --- Restructured package (feature 9) ---
        package: Dict[str, Any] = {
            "currency_analysis": {
                "denomination": denomination.denomination,
                "denomination_confidence": denomination.confidence,
                "denomination_matched_by": denomination.matched_by,
                "genuine_probability": risk_result["genuine_probability"],
                "counterfeit_probability": risk_result["counterfeit_probability"],
                "confidence": round(risk_result["genuine_probability"] * 100, 1),
                "risk": risk_result["risk"],
            },
            "visual_features": {
                "security_features": security_features,
                "missing_features": missing_features,
                "feature_consistency": consistency,
            },
            "feature_images": feature_images,
            "risk": {
                "score": risk_result["score"],
                "risk": risk_result["risk"],
                "genuine_probability": risk_result["genuine_probability"],
                "counterfeit_probability": risk_result["counterfeit_probability"],
                "feature_score_breakdown": risk_result["feature_breakdown"],
            },
            "serial_number": serial_result,
            "image_quality": {
                "quality": quality.quality,
                "quality_score": quality.quality_score,
                "blur_variance": quality.blur_variance,
                "mean_brightness": quality.mean_brightness,
                "resolution": quality.resolution,
                "issues": quality.issues,
                "note_rotated_for_analysis": was_rotated,
                "note_bounding_box": bounding_box,
            },
            "image_authenticity": authenticity,
            "explanation": explanation,
            "rbi_reference": rbi_reference,
            "pattern_id": pattern_info["pattern_id"],
            "counterfeit_pattern_match": pattern_info,
            "pipeline_stages": stages,
            "audit": audit_log,
            "visualization": visualization,
            "next_engine": "Fraud Intelligence Engine",
        }

        logger.info(
            "Currency analysis complete. denomination=%s risk=%s confidence=%.1f pattern_id=%s",
            denomination.denomination, risk_result["risk"], package["currency_analysis"]["confidence"], pattern_info["pattern_id"],
        )
        return package

    except CounterfeitIntelligenceError:
        raise
    except Exception as exc:
        logger.exception("Notebook 5 pipeline failed.")
        raise CounterfeitIntelligenceError(f"Notebook 5 pipeline failed: {exc}") from exc

# ## 21. Synthetic Sample Generation and Deterministic Test Suite
# 
# Real RBI note photographs are not bundled with this notebook (and should
# not be, for obvious reasons around currency image datasets). To
# demonstrate and test the full pipeline deterministically, this section
# synthesizes Rs 500-shaped test images with region-level texture control.
# This is a pipeline test fixture, not a claim about what real counterfeit
# notes look like.


def _add_texture(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], rng: np.random.Generator, density: float) -> None:
    '''Scatters small marks inside a region to simulate fine print detail.'''
    l, t, r, b = box
    n_marks = int((r - l) * (b - t) * density)
    for _ in range(n_marks):
        x = rng.integers(l, max(l + 1, r))
        y = rng.integers(t, max(t + 1, b))
        draw.point((x, y), fill=(0, 0, 0))


def _build_synthetic_note(
    path: str, base_color: Tuple[int, int, int], make_genuine: bool, seed: int, draw_numeral: Optional[str] = None,
) -> None:
    '''Builds a synthetic Rs 500-shaped test image with region-level texture control.'''
    width, height = 750, 330   # matches the Rs 500 aspect ratio (150mm x 66mm) at 5px/mm
    image = Image.new("RGB", (width, height), color=base_color)
    draw = ImageDraw.Draw(image)
    rng = np.random.default_rng(seed)

    for feature in ("portrait", "rbi_seal", "governor_signature"):
        box = _region_box_pixels(image, _FEATURE_REGIONS[feature])
        _add_texture(draw, box, rng, density=0.35)

    hard_density = 0.30 if make_genuine else 0.0
    for feature in ("security_thread", "watermark", "microprint", "ashoka_pillar"):
        box = _region_box_pixels(image, _FEATURE_REGIONS[feature])
        _add_texture(draw, box, rng, density=hard_density)

    serial_text = "3AK123456"
    for region_name in ("serial_number_top_left", "serial_number_bottom_right"):
        box = _region_box_pixels(image, _FEATURE_REGIONS[region_name])
        draw.text((box[0] + 2, box[1] + 2), serial_text, fill=(0, 0, 0))

    if draw_numeral:
        box = _region_box_pixels(image, _DENOMINATION_NUMERAL_REGION)
        draw.text((box[0] + 2, box[1] + 2), draw_numeral, fill=(0, 0, 0))

    image.save(path)


def run_notebook5_test_suite() -> Dict[str, Any]:
    sample_dir = "/tmp/notebook5_samples"
    os.makedirs(sample_dir, exist_ok=True)

    genuine_path = os.path.join(sample_dir, "synthetic_rs500_genuine.png")
    suspicious_path = os.path.join(sample_dir, "synthetic_rs500_suspicious.png")
    numeral_path = os.path.join(sample_dir, "synthetic_rs500_with_numeral.png")
    base_color = CONFIG.DENOMINATION_DOMINANT_COLOR["500"]

    _build_synthetic_note(genuine_path, base_color, make_genuine=True, seed=1)
    _build_synthetic_note(suspicious_path, base_color, make_genuine=False, seed=2)
    _build_synthetic_note(numeral_path, base_color, make_genuine=True, seed=3, draw_numeral="500")

    print("=== Notebook 5 Test Suite: synthetic Rs 500 notes ===\n")

    checks = []

    def _check(label: str, actual: Any, expected: Any) -> None:
        ok = actual == expected
        checks.append(ok)
        print(f"    [{'PASS' if ok else 'FAIL'}] {label}: expected={expected!r} actual={actual!r}")

    def _check_true(label: str, condition: bool) -> None:
        checks.append(condition)
        print(f"    [{'PASS' if condition else 'FAIL'}] {label}")

    print("--- Genuine-looking sample ---")
    genuine_package = analyze_currency_image(genuine_path)
    _check("denomination detected as Rs 500", genuine_package["currency_analysis"]["denomination"], "Rs 500")
    _check("genuine sample risk", genuine_package["currency_analysis"]["risk"], "Low")
    _check_true("genuine sample has no missing hard features",
                not any(f in genuine_package["visual_features"]["missing_features"] for f in ("security_thread", "watermark", "microprint")))
    _check("genuine sample consistency flag",
           genuine_package["visual_features"]["feature_consistency"]["inconsistent_pattern_detected"], False)

    print("\n--- Suspicious sample (hard features blanked out) ---")
    suspicious_package = analyze_currency_image(suspicious_path)
    _check_true("suspicious sample flags security_thread missing",
                "security_thread" in suspicious_package["visual_features"]["missing_features"])
    _check_true("suspicious sample flags watermark missing",
                "watermark" in suspicious_package["visual_features"]["missing_features"])
    _check_true("suspicious sample risk is Medium or High",
                suspicious_package["currency_analysis"]["risk"] in ("Medium", "High"))
    _check("suspicious sample consistency flag",
           suspicious_package["visual_features"]["feature_consistency"]["inconsistent_pattern_detected"], True)
    _check_true("suspicious sample genuine_probability lower than genuine sample's",
                suspicious_package["currency_analysis"]["genuine_probability"] < genuine_package["currency_analysis"]["genuine_probability"])
    _check_true("suspicious sample denomination still locked to Rs 500 despite blanked features",
                suspicious_package["currency_analysis"]["denomination"] == "Rs 500")

    # --- New checks: feature 1, security feature score ---
    thread_detail = genuine_package["visual_features"]["security_features"]["security_thread"]
    _check_true("security_thread carries a score/max_score pair", "score" in thread_detail and "max_score" in thread_detail)
    _check("security_thread max_score matches configured weight", thread_detail["max_score"], CONFIG.FEATURE_WEIGHTS["security_thread"])

    # --- New checks: feature 2, region crops ---
    _check("feature_images has an entry per region", len(genuine_package["feature_images"]), len(_FEATURE_REGIONS))
    _check_true("feature_images files actually exist on disk",
                all(os.path.exists(p) for p in genuine_package["feature_images"].values()))

    # --- New checks: feature 3, confidence heatmap ---
    _check_true("confidence heatmap file exists", os.path.exists(genuine_package["visualization"]["confidence_heatmap"]))
    _check_true("annotated image file exists", os.path.exists(genuine_package["visualization"]["annotated_image"]))

    # --- New checks: feature 4, serial intelligence ---
    _check_true("serial_number result carries ocr_confidence and serial_confidence keys",
                "ocr_confidence" in genuine_package["serial_number"] and "serial_confidence" in genuine_package["serial_number"])

    # --- New checks: feature 5, dependency graph ---
    graph = suspicious_package["visual_features"]["feature_consistency"]["dependency_graph"]
    _check("dependency graph has two clusters", len(graph["clusters"]), 2)
    _check_true("dependency graph flags cross-cluster conflict for suspicious sample", graph["cross_cluster_conflict"])

    # --- New checks: feature 6, image authenticity ---
    _check_true("image_authenticity has likely_source and indicators",
                "likely_source" in genuine_package["image_authenticity"] and "indicators" in genuine_package["image_authenticity"])

    # --- New checks: feature 7, quality score ---
    _check_true("image_quality carries a numeric quality_score", isinstance(genuine_package["image_quality"]["quality_score"], float))

    # --- New checks: feature 8, pipeline stage log ---
    _check("pipeline has 7 stages", len(genuine_package["pipeline_stages"]), 7)
    _check_true("pipeline stage order is correct",
                [s["stage"] for s in genuine_package["pipeline_stages"]] ==
                ["Input", "Quality Check", "Localized", "Rotated", "Denomination", "Features", "Consistency", "Risk"][:7])

    # --- New checks: feature 9, restructured package top-level keys ---
    expected_keys = {"currency_analysis", "visual_features", "feature_images", "risk", "serial_number",
                      "image_quality", "image_authenticity", "explanation", "rbi_reference", "pattern_id",
                      "counterfeit_pattern_match", "pipeline_stages", "audit", "visualization", "next_engine"}
    _check_true("restructured package contains all expected top-level groups",
                expected_keys.issubset(set(genuine_package.keys())))

    # --- New checks: feature 10, pattern ID ---
    _check_true("genuine sample pattern_id follows CT-### format", genuine_package["pattern_id"].startswith("CT-"))
    _check_true("suspicious sample known-pattern match references thread/watermark",
                "thread" in suspicious_package["counterfeit_pattern_match"]["known_pattern_match"].lower())

    print("\n--- Numeral cross-check sample (OCR-readable '500' drawn in the numeral region) ---")
    numeral_package = analyze_currency_image(numeral_path)
    _check("numeral sample denomination", numeral_package["currency_analysis"]["denomination"], "Rs 500")
    _check_true("numeral sample matched_by mentions OCR",
                any("ocr_numeral" in m for m in numeral_package["currency_analysis"]["denomination_matched_by"]))

    print(f"\nSUMMARY: {sum(checks)}/{len(checks)} checks passed\n")

    print("Genuine sample - full explanation:")
    for line in genuine_package["explanation"]:
        print(f"  - {line}")

    print("\nSuspicious sample - full explanation:")
    for line in suspicious_package["explanation"]:
        print(f"  - {line}")

    print("\nSuspicious sample pattern match:")
    print(json.dumps(suspicious_package["counterfeit_pattern_match"], indent=2))

    print("\nSuspicious sample pipeline stages:")
    for s in suspicious_package["pipeline_stages"]:
        print(f"  {s['stage']:14s} | {s['summary']}")

    print("\nRBI reference used for Rs 500:")
    print(f"  {genuine_package['rbi_reference']}")

    print("\nGenuine sample audit log:")
    print(json.dumps(genuine_package["audit"], indent=2))

    print("\nVisualization files:")
    print(f"  genuine annotated:    {genuine_package['visualization']['annotated_image']}")
    print(f"  genuine heatmap:      {genuine_package['visualization']['confidence_heatmap']}")
    print(f"  suspicious annotated: {suspicious_package['visualization']['annotated_image']}")
    print(f"  suspicious heatmap:   {suspicious_package['visualization']['confidence_heatmap']}")

    print(f"\nFeature crop files (genuine sample): {len(genuine_package['feature_images'])} saved")
    for feature, path in genuine_package["feature_images"].items():
        print(f"  {feature:28s} -> {path}")

    return {"genuine": genuine_package, "suspicious": suspicious_package, "numeral": numeral_package}


if __name__ == "__main__":
    run_notebook5_test_suite()