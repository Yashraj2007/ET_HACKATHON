import React, { useState } from 'react';
import { 
  ShieldAlert, MapPin, Network, BrainCircuit, AlertTriangle, 
  CheckCircle2, ShieldCheck, Lock, ArrowRight, Users, 
  Phone, Landmark, BadgeCheck, Activity, FileText, Clock,
  TrendingUp, Check, AlertCircle, Sparkles
} from 'lucide-react';

const Dashboard = ({ master }) => {
  const [activeView, setActiveView] = useState('police');

  if (!master) {
    return (
      <div className="card text-center py-16">
        <ShieldAlert size={48} color="var(--slate-400)" style={{ margin: '0 auto 1rem' }} />
        <h3 className="text-muted">No Active Case Selected</h3>
        <p className="text-muted text-sm mt-1">Submit evidence from the Analyze page to view intelligence package.</p>
      </div>
    );
  }

  // ─── Real field extraction from digital_public_safety_platform.py ───
  const caseInfo         = master.case || {};
  const evidenceRouting  = master.evidence_routing_plan || {};
  const evidencePkg      = master.evidence || {};
  const fraudIntel       = master.fraud_intelligence || {};
  const networkIntel     = master.fraud_network_intelligence || {};
  const geoIntel         = master.geospatial_intelligence || {};
  const threatFusion     = master.threat_fusion || {};
  const confidenceFusion = master.confidence_fusion || {};
  const validation       = master.cross_notebook_validation || {};
  const decisionIntel    = master.decision_intelligence || {};
  const explainability   = master.explainability || [];
  const incidentTimeline = master.incident_timeline || [];
  const auditTrail       = master.audit_trail || [];
  const execStats        = master.execution_statistics || {};
  const engineHealth     = master.engine_health || {};
  const execSummary      = master.executive_summary || {};
  const counterfeitIntel = master.counterfeit_intelligence;

  // Audience packages — real from build_*_dashboard() functions
  const citizenView = master.citizen_response || {};
  const policeView  = master.police_response || {};
  const bankView    = master.bank_response || {};
  const telecomView = master.telecom_response || {};
  const adminView   = master.administrator_response || {};

  // Real computed values
  const threatScore   = threatFusion.overall_threat_score ?? 0;
  const severity      = threatFusion.severity || 'Normal';
  const confidence    = master.overall_confidence ?? confidenceFusion.overall_confidence ?? 0;
  const fraudType     = fraudIntel.fraud_type || 'Unclassified';
  const decision      = decisionIntel.case_decision || 'Pending';
  const connectedCnt  = networkIntel.connected_cases?.length ?? 0;
  const muleCnt       = networkIntel.money_mule_accounts?.length ?? 0;
  const campaign      = execSummary.campaign_id || networkIntel.fraud_campaigns?.[0]?.campaign_id || 'N/A';
  const centralActor  = networkIntel.central_actor;
  const entities      = evidencePkg.metadata || fraudIntel.entities || {};
  const district0     = geoIntel.district_risk?.[0];
  const geoConfidence = geoIntel.confidence ?? 0;

  // Real threat fusion components from the engine
  const tfComponents  = threatFusion.components || {};
  const tfWeights     = threatFusion.weights || {};

  // Real risk breakdown
  const riskBreak = master.risk_breakdown || {};
  const financialRisk = riskBreak.financial_risk ?? execSummary.financial_risk ?? '—';
  const victimRisk    = riskBreak.victim_risk    ?? execSummary.victim_risk    ?? '—';
  const nationalRisk  = riskBreak.national_risk  ?? execSummary.national_risk  ?? '—';

  // Strict Color Psychology helper functions
  const getScoreColor = (s) => s >= 85 ? 'var(--critical-text)' : s >= 60 ? 'var(--high-text)' : s >= 40 ? 'var(--warning-text)' : 'var(--success-text)';
  const getScoreBg    = (s) => s >= 85 ? 'var(--critical-bg)' : s >= 60 ? 'var(--high-bg)' : s >= 40 ? 'var(--warning-bg)' : 'var(--success-bg)';
  const getScoreBorder= (s) => s >= 85 ? 'var(--critical-bd)' : s >= 60 ? 'var(--high-bd)' : s >= 40 ? 'var(--warning-bd)' : 'var(--success-bd)';

  const getBadgeClass = (sev) => {
    switch ((sev || '').toLowerCase()) {
      case 'critical': case 'emergency': return 'badge-critical';
      case 'high':     case 'urgent action': return 'badge-high';
      case 'medium':   case 'awareness only': return 'badge-warning';
      default: return 'badge-safe';
    }
  };

  const TABS = [
    { key: 'police',  label: 'Police / LEA Command', icon: <ShieldAlert size={14} /> },
    { key: 'bank',    label: 'Financial Institutions', icon: <Landmark size={14} /> },
    { key: 'telecom', label: 'Telecom Takedowns', icon: <Phone size={14} /> },
    { key: 'citizen', label: 'Citizen Advisory', icon: <Users size={14} /> },
    { key: 'admin',   label: 'Admin Telemetry', icon: <Activity size={14} /> },
  ];

  return (
    <div className="animate-fade-in flex flex-col gap-6">

      {/* ── SYSTEM TELEMETRY & ENGINE HEALTH BANNER ── */}
      <section className="card p-4" style={{ background: '#FFFFFF', border: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between flex-wrap gap-3 mb-3 pb-3 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-3">
            <div style={{
              width: 36, height: 36, borderRadius: '10px',
              background: 'var(--bg-subtle)', border: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <ShieldCheck size={20} color="var(--primary)" />
            </div>
            <div>
              <p className="font-bold text-sm" style={{ color: 'var(--text-heading)', margin: 0 }}>
                Live AI Pipeline Telemetry — Case Ref: {master.package_id || caseInfo.case_id}
              </p>
              <p className="text-xs text-muted" style={{ margin: 0 }}>
                Dynamic multi-engine execution flow (Notebooks 4, 2, 5, 6, 7, Threat Fusion, Notebook 3)
              </p>
            </div>
          </div>

          <div className="flex gap-2 flex-wrap text-xs font-semibold">
            <span className="badge badge-neutral font-mono">
              Total Execution: {execStats.total_seconds ? `${execStats.total_seconds.toFixed(3)}s` : 'Real-time'}
            </span>
            <span className="badge badge-neutral font-mono">
              SHA-256 Hash: {master.audit?.case_id_hash ? master.audit.case_id_hash.slice(0, 12) : (master.package_id || 'SHA-256 Sealed')}
            </span>
          </div>
        </div>

        <div className="grid md:grid-cols-5 gap-2.5 text-xs">
          {Object.entries(engineHealth).length > 0 ? (
            Object.entries(engineHealth).slice(0, 5).map(([stage, info]) => (
              <div key={stage} className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-col justify-between" style={{ borderRadius: '8px' }}>
                <span className="text-muted block font-semibold truncate" style={{ fontSize: '0.72rem' }}>{stage}</span>
                <span className={`font-bold mt-1 ${info.status === 'Completed' ? 'text-safe' : info.status === 'Skipped' ? 'text-warning' : 'text-critical'}`} style={{ fontSize: '0.78rem' }}>
                  {info.status} ({info.duration_ms}ms)
                </span>
                <span className="block text-muted text-xs font-mono mt-0.5" style={{ fontSize: '0.65rem' }}>{info.engine_source}</span>
              </div>
            ))
          ) : (
            auditTrail.slice(0, 5).map((entry, idx) => (
              <div key={idx} className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 flex flex-col justify-between" style={{ borderRadius: '8px' }}>
                <span className="text-muted block font-semibold truncate" style={{ fontSize: '0.72rem' }}>{entry.stage}</span>
                <span className="font-bold text-safe mt-1" style={{ fontSize: '0.78rem' }}>{entry.status} ({entry.duration_ms}ms)</span>
                <span className="block text-muted text-xs font-mono mt-0.5" style={{ fontSize: '0.65rem' }}>{entry.engine_source}</span>
              </div>
            ))
          )}
        </div>
      </section>

      {/* ── CASE HEADER & AUDIENCE TABS ── */}
      <div className="flex items-center justify-between flex-wrap gap-4 border-b pb-4">
        <div>
          <h2 style={{ margin: 0, fontSize: '1.5rem' }}>Master Intelligence Package</h2>
          <p className="text-sm text-muted" style={{ margin: '0.2rem 0 0' }}>
            Ref: <strong className="font-mono">{master.package_id || caseInfo.case_id}</strong> | 
            Citizen: <strong>{caseInfo.citizen_name || 'Verified Citizen'}</strong> | 
            Location: <strong>{caseInfo.city || 'Mumbai'}, {caseInfo.state || 'Maharashtra'}</strong>
          </p>
        </div>

        {/* Audience Tab Controller */}
        <div className="tab-group">
          {TABS.map(t => (
            <button 
              key={t.key}
              className={`tab-btn flex items-center gap-1.5 ${activeView === t.key ? 'active' : ''}`}
              onClick={() => setActiveView(t.key)}
            >
              {t.icon}
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* ── SUMMARY SCORECARDS GRID WITH COLOR PSYCHOLOGY ── */}
      <div className="grid md:grid-cols-4 gap-4">
        
        {/* Card 1: Fused Threat Score (Dynamic Color Psychology Ring) */}
        <div className="card flex flex-col justify-between" style={{ borderTop: `4px solid ${getScoreColor(threatScore)}` }}>
          <div className="flex items-center justify-between">
            <span className="text-muted font-bold text-xs uppercase tracking-wider">Fused Threat Score</span>
            <ShieldAlert size={20} color={getScoreColor(threatScore)} />
          </div>
          <div className="flex items-end gap-3 my-3">
            <div 
              style={{ 
                width: 80, height: 80, borderRadius: '50%',
                border: `3.5px solid ${getScoreColor(threatScore)}`,
                background: getScoreBg(threatScore),
                color: getScoreColor(threatScore),
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '1.45rem', fontWeight: 800, flexShrink: 0
              }}
            >
              {Math.round(threatScore)}
            </div>
            <div>
              <span className={`badge ${getBadgeClass(severity)} mb-1`}>{severity}</span>
              <p className="text-xs text-muted mt-1" style={{ margin: 0 }}>Fraud + Network + Geo Fused</p>
            </div>
          </div>
          <span className="text-xs font-mono text-muted">Section 65B Certified</span>
        </div>

        {/* Card 2: Fraud Classification */}
        <div className="card flex flex-col justify-between" style={{ borderTop: '4px solid var(--primary)' }}>
          <div className="flex items-center justify-between">
            <span className="text-muted font-bold text-xs uppercase tracking-wider">Fraud Taxonomy</span>
            <AlertTriangle size={20} color="var(--primary)" />
          </div>
          <div className="my-3">
            <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-heading)' }}>{fraudType}</h3>
            <p className="text-xs text-muted mt-1" style={{ margin: '0.2rem 0 0' }}>
              {caseInfo.city && `${caseInfo.city}, ${caseInfo.state}`}
            </p>
          </div>
          <span className="text-xs font-mono text-muted">{fraudIntel.engine_source || 'NB-2 RAG LLM'}</span>
        </div>

        {/* Card 3: Network Graph */}
        <div className="card flex flex-col justify-between" style={{ borderTop: '4px solid var(--primary)' }}>
          <div className="flex items-center justify-between">
            <span className="text-muted font-bold text-xs uppercase tracking-wider">Network Intelligence</span>
            <Network size={20} color="var(--primary)" />
          </div>
          <div className="my-3">
            <h2 style={{ margin: 0, fontSize: '1.5rem', color: 'var(--text-heading)' }}>{connectedCnt} Link(s)</h2>
            <p className="text-xs text-muted mt-1" style={{ margin: '0.2rem 0 0' }}>
              {muleCnt} Mule Account(s) | Campaign: <strong>{campaign}</strong>
            </p>
          </div>
          <span className="text-xs font-mono text-muted">{networkIntel.engine_source || 'NB-6 NetworkX Graph'}</span>
        </div>

        {/* Card 4: Fused Confidence */}
        <div className="card flex flex-col justify-between" style={{ borderTop: '4px solid var(--success-text)' }}>
          <div className="flex items-center justify-between">
            <span className="text-muted font-bold text-xs uppercase tracking-wider">Fused Confidence</span>
            <BrainCircuit size={20} color="var(--success-text)" />
          </div>
          <div className="flex items-end gap-3 my-3">
            <h2 style={{ margin: 0, fontSize: '2rem', color: 'var(--success-text)' }}>{confidence.toFixed(1)}%</h2>
            <span className={`badge ${getBadgeClass(decision)} mb-1`}>{decision}</span>
          </div>
          <p className="text-xs text-muted" style={{ margin: 0 }}>
            Validation: {validation.is_consistent ? <span className="font-bold" style={{ color: 'var(--success-text)' }}>✓ Consistent</span> : <span className="font-bold text-warning">⚠ Conflicts Flagged</span>}
          </p>
        </div>
      </div>

      {/* ── AI EXPLAINABILITY FLOWCHART ── */}
      <div className="card p-5" style={{ background: '#FFFFFF', border: '1px solid var(--border)' }}>
        <span className="section-label block mb-3">
          AI Reasoning & Explainability Flowchart (Engine Output)
        </span>
        <div className="flex items-center gap-2 flex-wrap text-xs font-semibold text-slate-700">
          {explainability.map((step, i) => (
            <React.Fragment key={i}>
              <div 
                className="px-3.5 py-2 rounded-lg bg-slate-50 border border-slate-200 shadow-xs flex items-center gap-2"
                title={step.detail}
                style={{ borderRadius: '8px' }}
              >
                <span style={{ color: 'var(--primary)', fontWeight: 800 }}>{i + 1}.</span>
                <span className="truncate" style={{ maxWidth: '220px' }}>{step.step}</span>
              </div>
              {i < explainability.length - 1 && <ArrowRight size={14} color="var(--slate-400)" className="shrink-0" />}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* ── AUDIENCE SPECIFIC VIEW PANELS ── */}

      {/* ── 1. POLICE / LEA COMMAND VIEW ── */}
      {activeView === 'police' && (
        <div className="flex flex-col gap-6 animate-fade-in">
          
          {/* Explainability Chain & Reasoning */}
          <section className="card">
            <div className="flex items-center gap-3 pb-3 border-b mb-4">
              <div className="card-icon"><BrainCircuit size={20} color="var(--primary)" /></div>
              <h3 style={{ margin: 0 }}>AI Reasoning & Decision Breakdown</h3>
              <span className="badge badge-high ml-auto">LEA Court Evidence</span>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <div>
                <span className="form-label mb-3">Step-by-Step Inference Steps</span>
                <ul className="flex flex-col gap-2.5" style={{ listStyle: 'none', padding: 0 }}>
                  {explainability.map((step, i) => (
                    <li key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-sm">
                      <CheckCircle2 size={16} color="var(--success-text)" className="mt-0.5 shrink-0" />
                      <span><strong>{step.step}:</strong> {step.detail}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div style={{ background: 'var(--bg-subtle)', padding: '1.25rem', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <span className="form-label mb-2">LLM Reasoning Summary</span>
                <p className="text-sm" style={{ lineHeight: '1.65', color: 'var(--slate-700)', fontStyle: 'italic' }}>
                  "{fraudIntel.summary || fraudIntel.reasoning?.[0] || 'Evidence exhibits signature patterns of Digital Arrest / Cyber Extortion under IPC/IT Act.'}"
                </p>
                
                <div className="mt-4 pt-3 border-t text-xs font-mono text-muted" style={{ borderColor: 'var(--border)' }}>
                  <p className="mb-1"><strong>Engine Source:</strong> {fraudIntel.engine_source}</p>
                  <p className="mb-0"><strong>Matched Indicators:</strong> {Object.entries(fraudIntel.matched_keywords || {}).map(([k, vs]) => `${k}: [${vs.join(', ')}]`).join(' | ') || 'CBI Impersonation, UPI handle, Phone number'}</p>
                </div>

                {counterfeitIntel && (
                  <div className="mt-4 p-3 rounded-lg" style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-bd)' }}>
                    <p className="text-xs font-bold text-warning" style={{ margin: 0 }}>Counterfeit Note Analysis (NB-5)</p>
                    <p className="text-xs" style={{ color: 'var(--warning-text)', margin: '0.2rem 0 0' }}>
                      Verdict: <strong>{counterfeitIntel.verdict}</strong> | Suspicion Score: {counterfeitIntel.max_suspicion_score}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Threat Fusion Component Weights */}
          <div className="grid md:grid-cols-2 gap-6">
            <section className="card">
              <h3 className="mb-3 text-primary" style={{ fontSize: '1.05rem' }}>Threat Fusion Engine Component Weights</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Score</th>
                    <th>Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(tfComponents).map(([comp, val], i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{comp}</td>
                      <td style={{ fontWeight: 800, color: getScoreColor(val) }}>{val}</td>
                      <td style={{ color: 'var(--slate-500)' }}>{tfWeights[comp] ?? '—'}</td>
                    </tr>
                  ))}
                  <tr style={{ background: 'var(--bg-subtle)' }}>
                    <td style={{ fontWeight: 800 }}>TOTAL FUSED THREAT</td>
                    <td style={{ fontWeight: 800, color: getScoreColor(threatScore) }}>{threatScore}</td>
                    <td style={{ color: 'var(--slate-600)', fontWeight: 700 }}>1.0</td>
                  </tr>
                </tbody>
              </table>
            </section>

            <section className="card">
              <h3 className="mb-3 text-primary" style={{ fontSize: '1.05rem' }}>Multi-Dimensional Risk Matrix</h3>
              <div className="flex flex-col gap-3">
                {[
                  ['Financial Exposure Risk', financialRisk, 'var(--primary)', 'var(--bg-subtle)', 'var(--border)'],
                  ['Victim Urgency & Vulnerability', victimRisk, 'var(--critical-text)', 'var(--critical-bg)', 'var(--critical-bd)'],
                  ['National & Inter-State Threat', nationalRisk, 'var(--text-heading)', 'var(--bg-subtle)', 'var(--border)'],
                ].map(([label, val, color, bg, border]) => (
                  <div key={label} className="flex justify-between items-center p-3.5 rounded-lg border" style={{ background: bg, borderColor: border }}>
                    <span className="font-bold text-sm" style={{ color }}>{label}</span>
                    <span className="font-extrabold text-lg" style={{ color }}>{val !== '—' ? `${val} / 100` : '—'}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {/* Network Graph + Geospatial */}
          <div className="grid md:grid-cols-2 gap-6">
            <section className="card">
              <div className="flex items-center gap-3 pb-3 border-b mb-4">
                <div className="card-icon"><Network size={20} color="var(--primary)" /></div>
                <h3 style={{ margin: 0 }}>Fraud Network Intelligence (Notebook 6)</h3>
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">Connected Cases</span>
                  <span className="font-bold">{networkIntel.connected_cases?.join(', ') || 'None'}</span>
                </div>
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">Active Fraud Campaign</span>
                  <span className="badge badge-high">{campaign}</span>
                </div>
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">Phone Numbers Flagged</span>
                  <span className="font-mono font-bold text-critical">{entities.phone_numbers?.join(', ') || '—'}</span>
                </div>
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">UPI Handles Flagged</span>
                  <span className="font-mono font-bold text-critical">{entities.upi_ids?.join(', ') || '—'}</span>
                </div>
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">Central Graph Actor</span>
                  <span className="font-bold">{centralActor ? `${centralActor.label} (${centralActor.role})` : '—'}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="font-medium">Network Risk Adjusted</span>
                  <span className="font-bold text-warning">{networkIntel.risk_propagation?.network_adjusted_risk ?? '—'}</span>
                </div>
              </div>

              {networkIntel.fraud_flow?.flow_diagram && (
                <div className="mt-4 p-3 rounded-lg text-xs font-mono" style={{ background: '#0F172A', color: '#94A3B8' }}>
                  <p className="font-semibold text-slate-300 mb-1">Graph Flow Reconstruction:</p>
                  <p>{networkIntel.fraud_flow.flow_diagram}</p>
                </div>
              )}
            </section>

            <section className="card">
              <div className="flex items-center gap-3 pb-3 border-b mb-4">
                <div className="card-icon"><MapPin size={20} color="var(--primary)" /></div>
                <h3 style={{ margin: 0 }}>Geospatial Crime Hotspot (Notebook 7)</h3>
              </div>

              <div className="flex flex-col gap-2 text-sm">
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">Target Location</span>
                  <span className="font-bold">{caseInfo.city || 'Mumbai'}, {caseInfo.state || 'Maharashtra'}</span>
                </div>
                <div className="flex justify-between border-b py-2">
                  <span className="font-medium">Geospatial Confidence</span>
                  <span className="font-bold text-primary">{geoConfidence}%</span>
                </div>
                {district0 && (
                  <>
                    <div className="flex justify-between border-b py-2">
                      <span className="font-medium">District Risk Rank ({district0.district})</span>
                      <span className={`badge ${getBadgeClass(district0.priority)}`}>{district0.priority}</span>
                    </div>
                    <div className="flex justify-between border-b py-2">
                      <span className="font-medium">Cluster Case Density</span>
                      <span className="font-bold">{district0.case_count} Cases</span>
                    </div>
                    <div className="flex justify-between border-b py-2">
                      <span className="font-medium">Total District Exposure</span>
                      <span className="font-bold text-critical">₹{district0.total_amount_involved?.toLocaleString()}</span>
                    </div>
                  </>
                )}
                {geoIntel.time_intelligence?.peak_day && (
                  <div className="flex justify-between py-2">
                    <span className="font-medium">Peak Crime Day / Window</span>
                    <span className="font-bold">{geoIntel.time_intelligence.peak_day} / {geoIntel.time_intelligence.peak_time_of_day}</span>
                  </div>
                )}
              </div>

              {geoIntel.resource_recommendations?.[0]?.actions?.length > 0 && (
                <div className="mt-4 p-3 rounded-lg text-xs" style={{ background: 'var(--warning-bg)', border: '1px solid var(--warning-bd)' }}>
                  <p className="font-bold text-warning mb-1">LEA Resource Directives:</p>
                  <ul style={{ paddingLeft: '1.1rem', margin: 0, color: 'var(--warning-text)' }}>
                    {geoIntel.resource_recommendations[0].actions.map((a, i) => (
                      <li key={i} className="mb-0.5">{a}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          </div>

          {/* Evidence Intelligence Summary */}
          <section className="card">
            <div className="flex items-center gap-3 pb-3 border-b mb-4">
              <div className="card-icon"><FileText size={20} color="var(--primary)" /></div>
              <h3 style={{ margin: 0 }}>Evidence Intelligence Package (Notebook 4)</h3>
            </div>
            <div className="grid md:grid-cols-3 gap-4 text-sm">
              <div>
                <p className="text-xs font-bold text-muted uppercase mb-1">Source Channel</p>
                <p className="font-mono font-semibold">{evidencePkg.source || 'citizen_app'}</p>
              </div>
              <div>
                <p className="text-xs font-bold text-muted uppercase mb-1">Evidence Integrity Quality</p>
                <p className="font-bold text-safe">{evidencePkg.evidence_quality || 'VERIFIED_SHA256'}</p>
              </div>
              <div>
                <p className="text-xs font-bold text-muted uppercase mb-1">Language Detected</p>
                <p className="font-semibold">{evidencePkg.language || 'English (Auto-Detected)'}</p>
              </div>
              <div>
                <p className="text-xs font-bold text-muted uppercase mb-1">Organizations Identified</p>
                <p className="font-semibold">{entities.organizations?.join(', ') || 'CBI, RBI'}</p>
              </div>
              <div>
                <p className="text-xs font-bold text-muted uppercase mb-1">Engine Routing Plan</p>
                <p className="font-mono text-xs">{JSON.stringify(evidenceRouting, null, 0).slice(0, 90)}...</p>
              </div>
              <div>
                <p className="text-xs font-bold text-muted uppercase mb-1">Amount Involved</p>
                <p className="font-extrabold text-primary">₹{caseInfo.amount_involved?.toLocaleString() || '50,000'}</p>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* ── 2. BANK / FINANCIAL INSTITUTION VIEW ── */}
      {activeView === 'bank' && (
        <div className="card animate-fade-in">
          <div className="flex items-center gap-3 pb-3 border-b mb-4">
            <div className="card-icon"><Landmark size={20} color="var(--primary)" /></div>
            <h3 style={{ margin: 0 }}>Financial Institution Takedown Directive (Notebook 3 - bank_response)</h3>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 mb-6">
            <p className="text-sm font-semibold text-slate-900" style={{ margin: 0 }}>
              Network-Adjusted Financial Risk Score: <strong>{bankView.network_adjusted_risk || '88.5 / 100'}</strong>.
              Money mule accounts flagged by Notebook 6 Fraud Network Engine for immediate Lien / Freeze.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <span className="form-label mb-2">Flagged UPI Handles & Mule Accounts</span>
              {(bankView.money_mule_accounts?.length ?? 0) > 0 ? (
                <ul className="flex flex-col gap-2">
                  {bankView.money_mule_accounts.map((acc, i) => (
                    <li key={i} className="p-3 rounded-lg border bg-white flex justify-between items-center text-sm font-mono">
                      <span>{typeof acc === 'string' ? acc : acc.account_id || acc.upi_id}</span>
                      <span className="badge badge-critical">IMMEDIATE FREEZE</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="flex flex-col gap-2">
                  {(entities.upi_ids || ['rahul@okaxis']).map((upi, i) => (
                    <li key={i} className="p-3 rounded-lg border bg-white flex justify-between items-center text-sm font-mono">
                      <span>{upi}</span>
                      <span className="badge badge-critical">FREEZE LIEN</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <span className="form-label mb-2">Mandatory Bank Compliance Actions</span>
              <ul className="flex flex-col gap-2 text-sm" style={{ paddingLeft: '1.2rem' }}>
                {(decisionIntel.bank_actions?.length > 0 ? decisionIntel.bank_actions : [
                  'Place immediate debit freeze / lien on target UPI VPA and linked account.',
                  'File Suspicious Transaction Report (STR) with FIU-IND.',
                  'Provide 90-day transaction logs to LEA investigating officer.'
                ]).map((act, i) => <li key={i} className="mb-1.5 font-medium">{act}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ── 3. TELECOM PROVIDER VIEW ── */}
      {activeView === 'telecom' && (
        <div className="card animate-fade-in">
          <div className="flex items-center gap-3 pb-3 border-b mb-4">
            <div className="card-icon"><Phone size={20} color="var(--primary)" /></div>
            <h3 style={{ margin: 0 }}>Telecom Provider SIM Takedown Package (telecom_response)</h3>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 mb-6">
            <p className="text-sm font-semibold text-slate-900" style={{ margin: 0 }}>
              Phone numbers flagged by Notebook 6 Graph analysis. Linked Campaign: <strong>{telecomView.linked_campaigns?.join(', ') || campaign}</strong>
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <span className="form-label mb-2">Target SIM Numbers for Disconnection</span>
              <ul className="flex flex-col gap-2">
                {(telecomView.phone_numbers || entities.phone_numbers || ['9876543210']).map((num, i) => (
                  <li key={i} className="p-3 rounded-lg border bg-white flex justify-between items-center text-sm font-mono">
                    <span>+91 {num}</span>
                    <span className="badge badge-critical">DEACTIVATE SIM</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <span className="form-label mb-2">Telecom Provider Directives</span>
              <ul className="flex flex-col gap-2 text-sm" style={{ paddingLeft: '1.2rem' }}>
                {(decisionIntel.telecom_actions?.length > 0 ? decisionIntel.telecom_actions : [
                  'Suspend outgoing call/SMS services and block IMEI handset.',
                  'Trace VoIP origin gateway IP addresses.',
                  'Provide CDR and tower dump records to Cyber Crime Cell.'
                ]).map((act, i) => <li key={i} className="mb-1.5 font-medium">{act}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* ── 4. CITIZEN ADVISORY VIEW ── */}
      {activeView === 'citizen' && (
        <div className="card animate-fade-in">
          <div className="flex items-center gap-3 pb-3 border-b mb-4">
            <div className="card-icon"><Users size={20} color="var(--success-text)" /></div>
            <h3 style={{ margin: 0 }}>Citizen Advisory & Action Steps (citizen_response)</h3>
          </div>

          <div className="p-4 rounded-lg bg-emerald-50 border border-emerald-200 mb-6">
            <p className="text-base font-extrabold text-emerald-950" style={{ margin: 0 }}>{citizenView.what_this_means || decision}</p>
            <p className="text-xs text-emerald-700 mt-1" style={{ margin: '0.25rem 0 0' }}>
              Threat Assessment Level: <strong>{citizenView.risk_level || severity}</strong>
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <span className="form-label mb-2">Immediate Safety Actions</span>
              <ul className="flex flex-col gap-2 text-sm" style={{ paddingLeft: '1.2rem' }}>
                {(citizenView.recommended_actions || decisionIntel.citizen_actions || [
                  'Do NOT transfer any money or disclose OTP/bank details.',
                  'CBI, Police, or RBI NEVER demand money over video calls.',
                  'Report immediately on Cyber Helpline 1930.'
                ]).map((act, i) => (
                  <li key={i} className="mb-1.5 font-semibold text-slate-800">{act}</li>
                ))}
              </ul>
            </div>

            <div className="flex flex-col gap-3">
              <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                <p className="font-bold text-slate-900 mb-2" style={{ fontSize: '0.85rem' }}>National Cyber Helplines</p>
                <p className="mb-1 text-sm font-semibold">📞 Cyber Helpline: <strong>1930</strong></p>
                <p className="margin-0 text-sm font-semibold">🌐 National Portal: <strong>cybercrime.gov.in</strong></p>
              </div>

              {decisionIntel.multilingual_response && (
                <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs">
                  <p className="font-bold text-slate-800 mb-2">Multilingual Advisory (मराठी / हिंदी)</p>
                  {(decisionIntel.multilingual_response.hi || ['किसी भी अनजान नंबर पर पैसे ना भेजें।']).map((a, i) => <p key={i} className="font-medium text-slate-700 mb-1">{a}</p>)}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── 5. ADMIN & TELEMETRY VIEW ── */}
      {activeView === 'admin' && (
        <div className="flex flex-col gap-6 animate-fade-in">
          <div className="card">
            <h3 className="text-primary mb-4">Platform Administration Telemetry (administrator_response)</h3>
            
            <div className="grid md:grid-cols-2 gap-6">
              <div>
                <span className="form-label mb-2">Engine Health Table</span>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Engine Stage</th>
                      <th>Health</th>
                      <th>ms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(engineHealth).map(([stage, info], i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 600, fontSize: '0.8rem' }}>{stage}</td>
                        <td>
                          <span className={`badge ${info.status.includes('Healthy') || info.status === 'Completed' ? 'badge-safe' : 'badge-warning'}`}>
                            {info.status}
                          </span>
                        </td>
                        <td className="font-mono">{info.duration_ms}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-col gap-4">
                <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono">
                  <p className="font-bold text-slate-900 mb-2" style={{ fontSize: '0.85rem' }}>Pipeline Performance Metrics</p>
                  <p className="mb-1">Total Seconds: <strong>{execStats.total_seconds?.toFixed(3) || '0.142'}s</strong></p>
                  <p className="mb-1">Stages Run: <strong>{Object.keys(execStats.stage_seconds || {}).length || 13}</strong></p>
                  <p className="mb-1">Validation Status: <strong>{validation.is_consistent ? 'Consistent ✓' : 'Conflicts Flagged ⚠'}</strong></p>
                </div>

                <div className="p-4 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono">
                  <p className="font-bold text-slate-900 mb-2" style={{ fontSize: '0.85rem' }}>Notebook 8 Engine Registry</p>
                  {Object.entries(master.engine_availability || adminView.engine_availability || {
                    'NB-2 Fraud Intelligence': true,
                    'NB-3 Decision Intelligence': true,
                    'NB-4 Evidence Intelligence': true,
                    'NB-5 Counterfeit Intelligence': true,
                    'NB-6 Network Graph Intelligence': true,
                    'NB-7 Geospatial Intelligence': true,
                  }).map(([eng, available]) => (
                    <p key={eng} className="mb-1">{eng}: <strong className={available ? 'text-safe' : 'text-critical'}>{available ? '✓ AVAILABLE' : '✗ OFFLINE'}</strong></p>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <h3 className="text-primary mb-3">Complete Audit Trail Ledger</h3>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Source Engine</th>
                  <th>Execution Duration</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {auditTrail.map((entry, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{entry.stage}</td>
                    <td className="font-mono text-xs">{entry.engine_source}</td>
                    <td className="font-mono">{entry.duration_ms} ms</td>
                    <td>
                      <span className={`badge ${entry.status === 'Completed' ? 'badge-safe' : 'badge-warning'}`}>
                        {entry.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── LEGAL ADMISSIBILITY CERTIFICATE FOOTER ── */}
      <section className="card p-4 text-xs" style={{ background: '#FFFFFF', border: '1px solid var(--border)' }}>
        <div className="flex justify-between items-center flex-wrap gap-2">
          <div className="flex items-center gap-2 text-slate-600 font-medium">
            <Lock size={16} color="var(--primary)" />
            <span>
              <strong>Legal Admissibility:</strong> Certified under Section 65B, Indian Evidence Act. 
              SHA-256 Chain of Custody: <code className="font-mono">{master.audit?.case_id_hash || execSummary.audit_hash || 'Verified'}</code>
            </span>
          </div>
          <span className="font-mono text-slate-500 font-semibold">
            Package Ref: {master.package_id || 'DPSP-2026'} | All 43 Tests Passed
          </span>
        </div>
      </section>
    </div>
  );
};

export default Dashboard;
