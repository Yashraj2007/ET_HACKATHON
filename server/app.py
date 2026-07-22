import asyncio
import json
import logging
import os
import sys
import shutil
import uuid

# ─── CRITICAL: Import from c_m/server/ (the real Notebook 8 orchestrator) ───
# c_m/server/ is the canonical source of truth for all intelligence engines.
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "c_m", "server"))
if not os.path.exists(_SERVER_DIR):
    _SERVER_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, _SERVER_DIR)

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

import digital_public_safety_platform as dpsp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dpsp_api")

app = FastAPI(
    title="Digital Public Safety Platform API",
    description="Multi-Modal AI Intelligence Engine Backend (c_m/server - Notebook 8 Revision 4)",
    version="4.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reports dir: save generated PDFs inside c_m/server/reports/
UPLOAD_DIR  = os.path.join(_SERVER_DIR, "uploads")
REPORTS_DIR = os.path.join(_SERVER_DIR, "reports")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# In-memory store for active analysis tasks and progress streams
TASKS: Dict[str, Dict[str, Any]] = {}

# ─── Persistent on-disk case store ───────────────────────────────────────────
# Cases are saved as individual JSON files under REPORTS_DIR/cases_cache/
# so they survive server restarts and can always be downloaded.
CASES_CACHE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "cases_cache")
os.makedirs(CASES_CACHE_DIR, exist_ok=True)

def _case_cache_path(case_id: str) -> str:
    safe = case_id.replace("/", "_").replace(" ", "_")
    return os.path.join(CASES_CACHE_DIR, f"{safe}.json")

def save_case_to_disk(case_id: str, pkg: Dict[str, Any]) -> None:
    """Persist a master package to disk so it survives restarts."""
    try:
        path = _case_cache_path(case_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pkg, f, default=str)
        logger.info("Case saved to disk: %s -> %s", case_id, path)
    except Exception as exc:
        logger.warning("Could not persist case %s to disk: %s", case_id, exc)

def load_case_from_disk(case_id: str) -> Optional[Dict[str, Any]]:
    """Load a previously persisted master package from disk."""
    try:
        path = _case_cache_path(case_id)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Could not load case %s from disk: %s", case_id, exc)
    return None

def load_all_cases_from_disk() -> None:
    """At startup: reload all persisted cases into CASE_REGISTRY."""
    loaded = 0
    try:
        for fname in os.listdir(CASES_CACHE_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(CASES_CACHE_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                # Recover case_id from the package itself
                cid = pkg.get("case", {}).get("case_id") or fname[:-5]
                if cid and cid not in dpsp.CASE_REGISTRY.master_packages:
                    dpsp.CASE_REGISTRY.register_master_package(cid, pkg)
                    loaded += 1
            except Exception as exc:
                logger.warning("Skipping corrupt cache file %s: %s", fname, exc)
    except Exception as exc:
        logger.warning("Could not scan cases_cache dir: %s", exc)
    if loaded:
        logger.info("Restored %d persisted cases from disk cache.", loaded)


def _do_preload():
    """Pre-run all 5 official synthetic benchmark cases from digital_public_safety_platform.py
    so the Dashboard has real data as soon as the server starts."""
    logger.info("Pre-loading all 5 synthetic benchmark cases from c_m/server/...")
    try:
        synth_cases = dpsp._build_synthetic_cases()
        for case in synth_cases:
            if case.case_id not in dpsp.CASE_REGISTRY.master_packages:
                pkg = dpsp.process_case(case, report_dir=REPORTS_DIR)
                tf = pkg.get("threat_fusion", {})
                save_case_to_disk(case.case_id, pkg)  # persist so downloads survive restart
                logger.info(
                    f"Pre-loaded: {case.case_id} | "
                    f"Threat={tf.get('overall_threat_score')} | "
                    f"Decision={pkg.get('decision_intelligence', {}).get('case_decision')}"
                )
    except Exception as e:
        logger.error(f"Error pre-loading benchmark cases: {e}", exc_info=True)

@app.on_event("startup")
async def preload_benchmark_cases():
    import threading
    # First reload any previously persisted cases
    load_all_cases_from_disk()
    # Then pre-load synthetic benchmark cases in background
    threading.Thread(target=_do_preload, daemon=True).start()

STAGES_ORDER = [
    "Case Intake",
    "Evidence Routing",
    "Notebook 4 - Evidence Intelligence",
    "Notebook 2 - Fraud Intelligence",
    "Notebook 5 - Counterfeit Intelligence",
    "Notebook 6 - Fraud Network Intelligence",
    "Notebook 7 - Geospatial Intelligence",
    "Threat Fusion Engine",
    "Confidence Fusion Engine",
    "Cross-Notebook Validation",
    "Notebook 3 - Decision Intelligence",
    "Explainability",
    "Final Report Generation"
]

def run_analysis_task(task_id: str, raw_case: dpsp.CaseIntake):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def on_stage_progress(stage_name: str, duration_ms: float, status: str):
        if stage_name in STAGES_ORDER:
            idx = STAGES_ORDER.index(stage_name) + 1
            percent = int((idx / len(STAGES_ORDER)) * 100)
        else:
            percent = 50

        event_data = {
            "type": "progress",
            "stage": stage_name,
            "duration_ms": duration_ms,
            "status": status,
            "percent": min(95, percent)
        }
        TASKS[task_id]["events"].append(event_data)
        logger.info(f"Task {task_id} progress: {stage_name} ({duration_ms}ms) -> {percent}%")

    try:
        try:
            master_package = dpsp.process_case(
                raw_case=raw_case,
                report_dir=REPORTS_DIR,
                progress_callback=on_stage_progress
            )
        except TypeError:
            logger.warning("process_case did not accept progress_callback argument, calling standard process_case")
            master_package = dpsp.process_case(
                raw_case=raw_case,
                report_dir=REPORTS_DIR
            )
        
        # Save master package into registry
        dpsp.CASE_REGISTRY.register_master_package(raw_case.case_id, master_package)
        # Persist to disk so it survives restarts
        save_case_to_disk(raw_case.case_id, master_package)
        
        # Mark task as completed
        TASKS[task_id]["status"] = "completed"
        TASKS[task_id]["result"] = master_package
        TASKS[task_id]["events"].append({
            "type": "complete",
            "percent": 100,
            "case_id": raw_case.case_id,
            "result": master_package
        })
    except Exception as e:
        logger.error(f"Error executing case analysis for task {task_id}: {e}", exc_info=True)
        TASKS[task_id]["status"] = "failed"
        TASKS[task_id]["error"] = str(e)
        TASKS[task_id]["events"].append({
            "type": "error",
            "error": str(e)
        })

@app.post("/api/analyze")
async def analyze_case(
    background_tasks: BackgroundTasks,
    content: str = Form(""),
    citizen_name: str = Form("Citizen Reporter"),
    city: str = Form("Mumbai"),
    state: str = Form("Maharashtra"),
    priority: str = Form("Normal"),
    amount_involved: float = Form(0.0),
    is_currency: bool = Form(False),
    case_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(None),
):
    # If user chose an official benchmark case, just re-run that exact case
    if not case_id:
        case_id = f"CASE-{dpsp.datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"

    task_id = str(uuid.uuid4())
    evidence_items: List[dpsp.EvidenceItem] = []

    # Read uploaded files
    if files:
        for file in files:
            if not file.filename:
                continue
            saved_path = os.path.join(UPLOAD_DIR, f"{case_id}_{file.filename}")
            with open(saved_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            ext = os.path.splitext(file.filename)[1].lower()
            if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                ev_type = "currency_image" if is_currency else "whatsapp_screenshot"
            elif ext in [".pdf", ".doc", ".docx", ".txt"]:
                ev_type = "document"
            elif ext in [".mp3", ".wav", ".m4a"]:
                ev_type = "call_recording"
            elif ext in [".mp4", ".mov", ".avi"]:
                ev_type = "video"
            else:
                ev_type = "text"

            extracted_text = content
            if ext in [".txt"]:
                try:
                    with open(saved_path, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()
                except Exception:
                    pass

            evidence_items.append(
                dpsp.EvidenceItem(
                    evidence_type=ev_type,
                    content=extracted_text or f"Uploaded file: {file.filename}",
                    metadata={
                        "file_path": saved_path,
                        "original_filename": file.filename,
                        "source_channel": "citizen_upload",
                        "citizen_reported_suspicious": is_currency or "scam" in (content or "").lower(),
                    }
                )
            )

    # Add direct text evidence
    if content or not evidence_items:
        ev_type = "call_recording" if ("caller" in content.lower() or "cbi" in content.lower() or "rbi" in content.lower()) else "text"
        evidence_items.append(
            dpsp.EvidenceItem(
                evidence_type=ev_type,
                content=content or "Citizen reported suspicious communication received.",
                metadata={"source_channel": "web_intake"}
            )
        )
    
    # If currency flag, add a currency_image evidence item too
    if is_currency and not any(e.evidence_type == "currency_image" for e in evidence_items):
        evidence_items.append(
            dpsp.EvidenceItem(
                evidence_type="currency_image",
                content=content or "Suspicious currency note reported by citizen.",
                metadata={"source_channel": "currency_image", "citizen_reported_suspicious": True}
            )
        )

    raw_case = dpsp.CaseIntake(
        case_id=case_id,
        citizen_name=citizen_name,
        timestamp=dpsp.datetime.now(dpsp.timezone.utc).isoformat(),
        city=city,
        state=state,
        priority=priority,
        amount_involved=amount_involved,
        evidence=evidence_items,
        source="citizen_app"
    )

    TASKS[task_id] = {
        "task_id": task_id,
        "case_id": case_id,
        "status": "processing",
        "events": [],
        "result": None,
        "error": None
    }

    background_tasks.add_task(run_analysis_task, task_id, raw_case)

    return {
        "status": "started",
        "task_id": task_id,
        "case_id": case_id
    }

@app.get("/api/analyze/stream/{task_id}")
async def stream_analysis(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        sent_count = 0
        while True:
            task = TASKS.get(task_id)
            if not task:
                break
            
            events = task["events"]
            while sent_count < len(events):
                event = events[sent_count]
                sent_count += 1
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    return
            
            if task["status"] in ("completed", "failed") and sent_count >= len(events):
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/case/{case_id}")
async def get_case(case_id: str):
    """Return the FULL master package for a given case_id - all real engine outputs."""
    package = _lookup_pkg(case_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    return package

@app.get("/api/cases")
async def list_cases():
    """List all processed cases with their real engine outputs summary."""
    # Ensure any disk-persisted cases are in the registry
    load_all_cases_from_disk()
    cases_summary = []
    for case_id, pkg in dpsp.CASE_REGISTRY.master_packages.items():

        case_info = pkg.get("case", {})
        threat_info = pkg.get("threat_fusion", {})
        decision_info = pkg.get("decision_intelligence", {})
        risk_breakdown = pkg.get("risk_breakdown", {})
        network_info = pkg.get("fraud_network_intelligence", {})
        geo_info = pkg.get("geospatial_intelligence", {})
        fraud_info = pkg.get("fraud_intelligence", {})
        exec_stats = pkg.get("execution_statistics", {})
        audit = pkg.get("audit", {})
        
        cases_summary.append({
            "case_id": case_id,
            "timestamp": case_info.get("timestamp"),
            "citizen_name": case_info.get("citizen_name"),
            "city": case_info.get("city"),
            "state": case_info.get("state"),
            # Real threat fusion fields
            "threat_score": threat_info.get("overall_threat_score"),
            "severity": threat_info.get("severity"),
            "threat_level": threat_info.get("threat_level"),
            "confidence": pkg.get("overall_confidence"),
            # Real fraud intelligence
            "fraud_type": fraud_info.get("fraud_type"),
            "engine_source": fraud_info.get("engine_source"),
            # Real decision
            "decision": decision_info.get("case_decision") or decision_info.get("decision_category"),
            "escalate": decision_info.get("escalate"),
            "stakeholders": decision_info.get("stakeholders"),
            # Real risk breakdown
            "financial_risk": risk_breakdown.get("financial_risk"),
            "victim_risk": risk_breakdown.get("victim_risk"),
            "national_risk": risk_breakdown.get("national_risk"),
            # Real network
            "connected_cases": len(network_info.get("connected_cases", [])),
            "money_mule_flag": pkg.get("money_mule_flagged"),
            "campaign_id": network_info.get("campaign_id"),
            # Real geo
            "hotspot": geo_info.get("hotspots", [None])[0] if geo_info.get("hotspots") else None,
            # Stats
            "total_seconds": exec_stats.get("total_seconds"),
            "audit_hash": audit.get("case_id_hash"),
            "has_report": bool(pkg.get("final_report") and os.path.exists(pkg.get("final_report", ""))),
        })
    
    # Sort by threat score descending (most critical first)
    cases_summary.sort(key=lambda x: x.get("threat_score") or 0, reverse=True)
    return cases_summary

def _lookup_pkg(case_id: str) -> Optional[Dict[str, Any]]:
    """Look up a master package: memory registry → active tasks → disk cache."""
    pkg = dpsp.CASE_REGISTRY.master_packages.get(case_id)
    if pkg:
        return pkg
    for t in TASKS.values():
        if t.get("case_id") == case_id and t.get("result"):
            return t["result"]
    return load_case_from_disk(case_id)


@app.get("/api/case/{case_id}/report")
async def download_report(case_id: str):
    """Download the ReportLab PDF (or plain-text fallback) for a case."""
    pkg = _lookup_pkg(case_id)

    if not pkg:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found. It may have been lost after a server restart.")


    report_path = pkg.get("final_report") or pkg.get("final_intelligence_report_path")

    # Check for .pdf first, then .txt fallback (when reportlab is not installed)
    if report_path and os.path.exists(report_path):
        ext = os.path.splitext(report_path)[1].lower()
        media_type = "application/pdf" if ext == ".pdf" else "text/plain"
        filename = os.path.basename(report_path)
        return FileResponse(report_path, filename=filename, media_type=media_type,
                            headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    # Try the sibling .txt fallback
    if report_path:
        txt_path = os.path.splitext(report_path)[0] + ".txt"
        if os.path.exists(txt_path):
            filename = os.path.basename(txt_path)
            return FileResponse(txt_path, filename=filename, media_type="text/plain",
                                headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    # Last resort: generate and stream a plain-text report on-the-fly
    lines = dpsp._build_final_report_text_lines(pkg) if hasattr(dpsp, '_build_final_report_text_lines') else []
    if not lines:
        # Build a minimal text report from available fields
        case_info = pkg.get("case", {})
        threat = pkg.get("threat_fusion", {})
        decision = pkg.get("decision_intelligence", {})
        exec_summary = pkg.get("executive_summary", {})
        lines = [
            "DIGITAL PUBLIC SAFETY PLATFORM — INTELLIGENCE REPORT",
            "ET AI Hackathon 2026 | Problem Statement 6 (PS6)",
            "=" * 70,
            f"Case Ref: {case_id}",
            f"Citizen: {case_info.get('citizen_name', 'Verified Citizen')}",
            f"City: {case_info.get('city', 'Mumbai')}, {case_info.get('state', 'Maharashtra')}",
            f"Timestamp: {case_info.get('timestamp', 'N/A')}",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
        ]
        for k, v in exec_summary.items():
            lines.append(f"  {k}: {v}")
        lines += [
            "",
            "THREAT FUSION SCORE",
            "-" * 40,
            f"  Overall Threat Score: {threat.get('overall_threat_score', 'N/A')}",
            f"  Severity: {threat.get('severity', 'N/A')}",
            "",
            "DECISION",
            "-" * 40,
            f"  Case Decision: {decision.get('case_decision', 'N/A')}",
            f"  Escalate: {decision.get('escalate', False)}",
            "",
            "LEGAL ADMISSIBILITY",
            "-" * 40,
            f"  SHA-256 Hash: {pkg.get('audit', {}).get('case_id_hash', 'N/A')}",
            "  Certified under Section 65B Indian Evidence Act",
            "",
            "Generated by DPSP Intelligence Engine (Notebook 8 Rev 4)",
        ]

    report_bytes = "\n".join(lines).encode("utf-8")
    safe_case_id = case_id.replace("/", "-").replace(" ", "_")
    filename = f"DPSP_Intelligence_Report_{safe_case_id}.txt"
    return StreamingResponse(
        iter([report_bytes]),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/case/{case_id}/download/json")
async def download_report_json(case_id: str):
    """Download the full master intelligence package as JSON."""
    pkg = _lookup_pkg(case_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    import json as _json
    safe_case_id = case_id.replace("/", "-").replace(" ", "_")
    filename = f"DPSP_Master_Package_{safe_case_id}.json"
    json_bytes = _json.dumps(pkg, indent=2, default=str).encode("utf-8")
    return StreamingResponse(
        iter([json_bytes]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/case/{case_id}/download/html")
async def download_report_html(case_id: str):
    """Generate and download a styled HTML intelligence report."""
    pkg = _lookup_pkg(case_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")


    case_info     = pkg.get("case", {})
    threat        = pkg.get("threat_fusion", {})
    decision      = pkg.get("decision_intelligence", {})
    exec_summary  = pkg.get("executive_summary", {})
    fraud_intel   = pkg.get("fraud_intelligence", {})
    network_intel = pkg.get("fraud_network_intelligence", {})
    geo_intel     = pkg.get("geospatial_intelligence", {})
    explainability= pkg.get("explainability", [])
    audit         = pkg.get("audit", {})
    audit_trail   = pkg.get("audit_trail", [])
    exec_stats    = pkg.get("execution_statistics", {})

    score = threat.get('overall_threat_score', 0)
    score_color = '#991B1B' if score >= 85 else '#C2410C' if score >= 60 else '#B45309' if score >= 40 else '#047857'
    score_bg    = '#FEF2F2' if score >= 85 else '#FFF7ED' if score >= 60 else '#FFFBEB' if score >= 40 else '#ECFDF5'

    audit_rows = "".join(
        f"<tr><td>{e.get('stage','')}</td><td>{e.get('engine_source','')}</td>"
        f"<td>{e.get('duration_ms','')} ms</td><td>{e.get('status','')}</td></tr>"
        for e in audit_trail
    )
    explain_rows = "".join(
        f"<li><strong>{s.get('step','')}:</strong> {s.get('detail','')}</li>"
        for s in explainability
    )
    police_actions = "".join(f"<li>{a}</li>" for a in (decision.get('police_actions') or []))
    bank_actions   = "".join(f"<li>{a}</li>" for a in (decision.get('bank_actions') or []))
    telecom_actions= "".join(f"<li>{a}</li>" for a in (decision.get('telecom_actions') or []))
    citizen_actions= "".join(f"<li>{a}</li>" for a in (decision.get('citizen_actions') or []))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>DPSP Intelligence Report — {case_id}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #F8FAFC; color: #1E293B; font-size: 13px; }}
    .wrapper {{ max-width: 900px; margin: 40px auto; background: #fff; border: 1px solid #E2E8F0; border-radius: 12px; overflow: hidden; }}
    .header {{ background: #0F172A; color: #fff; padding: 32px 40px; text-align: center; }}
    .header h1 {{ font-size: 22px; font-weight: 800; letter-spacing: -0.5px; margin-bottom: 6px; }}
    .header p {{ font-size: 12px; color: #94A3B8; }}
    .badge {{ display: inline-block; padding: 4px 12px; border-radius: 100px; font-size: 11px; font-weight: 700; background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }}
    .body {{ padding: 36px 40px; }}
    .score-ring {{ display: inline-flex; align-items: center; justify-content: center; width: 80px; height: 80px; border-radius: 50%; border: 4px solid {score_color}; background: {score_bg}; font-size: 20px; font-weight: 800; color: {score_color}; margin-bottom: 12px; }}
    h2 {{ font-size: 14px; font-weight: 700; color: #0F172A; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 2px solid #E2E8F0; padding-bottom: 6px; margin: 28px 0 12px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }}
    th {{ text-align: left; padding: 8px 12px; background: #F1F5F9; color: #64748B; font-size: 11px; font-weight: 700; text-transform: uppercase; border-bottom: 1px solid #E2E8F0; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid #F1F5F9; vertical-align: top; }}
    .kv {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .kv-item {{ background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 14px; }}
    .kv-item .label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; color: #94A3B8; margin-bottom: 3px; }}
    .kv-item .value {{ font-size: 14px; font-weight: 800; color: #0F172A; }}
    ul {{ padding-left: 20px; line-height: 1.8; }}
    .critical {{ color: #991B1B; }} .warning {{ color: #C2410C; }} .safe {{ color: #047857; }}
    .footer {{ background: #F1F5F9; border-top: 1px solid #E2E8F0; padding: 20px 40px; text-align: center; font-size: 11px; color: #64748B; }}
    @media print {{
      body {{ background: #fff; }}
      .wrapper {{ border: none; margin: 0; border-radius: 0; }}
    }}
  </style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <div class="badge">ET AI Hackathon 2026 · Problem Statement 6 (PS6)</div>
    <h1 style="margin-top:12px">Digital Public Safety Intelligence Report</h1>
    <p>Notebook 8 Rev 4 · 6 AI Engines Fused | Case Ref: {case_id}</p>
    <p style="margin-top:6px; font-family: monospace; font-size: 11px;">SHA-256: {audit.get('case_id_hash','N/A')} · Section 65B Certified</p>
  </div>

  <div class="body">

    <h2>Case Overview</h2>
    <div class="kv">
      <div class="kv-item"><div class="label">Citizen</div><div class="value">{case_info.get('citizen_name','N/A')}</div></div>
      <div class="kv-item"><div class="label">Location</div><div class="value">{case_info.get('city','N/A')}, {case_info.get('state','N/A')}</div></div>
      <div class="kv-item"><div class="label">Fraud Type</div><div class="value">{fraud_intel.get('fraud_type','N/A')}</div></div>
      <div class="kv-item"><div class="label">Amount Involved</div><div class="value">₹{str(case_info.get('amount_involved',0))}</div></div>
      <div class="kv-item"><div class="label">Priority</div><div class="value">{case_info.get('priority','Normal')}</div></div>
      <div class="kv-item"><div class="label">Timestamp</div><div class="value">{case_info.get('timestamp','N/A')[:19]}</div></div>
    </div>

    <h2>Threat Fusion Score</h2>
    <div style="display:flex; align-items:center; gap:24px; flex-wrap:wrap;">
      <div class="score-ring">{round(score)}</div>
      <div>
        <p><strong>Severity:</strong> {threat.get('severity','N/A')}</p>
        <p><strong>Fused Confidence:</strong> {pkg.get('overall_confidence', 'N/A')}%</p>
        <p><strong>Case Decision:</strong> <span class="{'critical' if 'urgent' in str(decision.get('case_decision','')).lower() else 'safe'}">{decision.get('case_decision','N/A')}</span></p>
      </div>
    </div>

    <h2>AI Explainability Chain</h2>
    <ol style="padding-left:20px; line-height:2;">{explain_rows}</ol>

    <h2>Stakeholder Action Directives</h2>
    {'<p><strong style="color:#1E40AF">Police / LEA Actions:</strong></p><ul>' + police_actions + '</ul>' if police_actions else ''}
    {'<p><strong style="color:#065F46">Bank / Financial Actions:</strong></p><ul>' + bank_actions + '</ul>' if bank_actions else ''}
    {'<p><strong style="color:#6D28D9">Telecom Takedown Actions:</strong></p><ul>' + telecom_actions + '</ul>' if telecom_actions else ''}
    {'<p><strong style="color:#B45309">Citizen Advisory:</strong></p><ul>' + citizen_actions + '</ul>' if citizen_actions else ''}

    <h2>Audit Trail</h2>
    <table>
      <thead><tr><th>Stage</th><th>Engine Source</th><th>Duration</th><th>Status</th></tr></thead>
      <tbody>{audit_rows}</tbody>
    </table>

    <h2>Execution Statistics</h2>
    <p><strong>Total Pipeline Time:</strong> {exec_stats.get('total_seconds','N/A')}s</p>

  </div>

  <div class="footer">
    <p><strong>CONFIDENTIAL — LAW ENFORCEMENT & PUBLIC SAFETY DOCUMENT</strong></p>
    <p style="margin-top:4px">Generated by digital_public_safety_platform.py (Notebook 8, Rev 4) · ET AI Hackathon 2026</p>
    <p style="margin-top:4px; font-family:monospace; font-size:10px">SHA-256 Chain of Custody: {audit.get('case_id_hash','N/A')}</p>
  </div>
</div>
</body>
</html>"""

    safe_case_id = case_id.replace("/", "-").replace(" ", "_")
    filename = f"DPSP_Intelligence_Report_{safe_case_id}.html"
    return StreamingResponse(
        iter([html.encode("utf-8")]),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.get("/api/engine-registry")
async def get_engine_registry():
    """Return the real engine registry from the administrator_response of the latest case."""
    if dpsp.CASE_REGISTRY.master_packages:
        latest = list(dpsp.CASE_REGISTRY.master_packages.values())[-1]
        admin_view = latest.get("administrator_response", {})
        return {
            "engine_registry": admin_view.get("engine_registry", []),
            "availability": admin_view.get("notebook_availability", {}),
        }
    return {"engine_registry": [], "availability": {}}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
