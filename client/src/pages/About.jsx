import React from 'react';
import { ShieldCheck, Cpu, Network, MapPin, Lock, FileSearch, CheckCircle2, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const ENGINES_INFO = [
  { nb: 'Notebook 2', title: 'AI Fraud Intelligence Engine', desc: 'RAG-backed LLM vector search across 8 scam taxonomies (Digital Arrest, UPI Fraud, Job Scam, etc.) with explainability chains.', color: 'var(--critical)' },
  { nb: 'Notebook 3', title: 'Decision Intelligence & Directives', desc: 'Synthesizes fused threat scores into legal incident reports, stakeholder directives for Police, Banks, Telecom, and Citizens.', color: 'var(--warning)' },
  { nb: 'Notebook 4', title: 'Multi-Modal Evidence Extraction', desc: 'Ingests PDFs, OCR images, audio clips, and chat transcripts while verifying SHA-256 integrity and extracting entities.', color: 'var(--primary)' },
  { nb: 'Notebook 5', title: 'Counterfeit Currency Detector', desc: 'Automated RBI security feature checklist verification (security thread, watermark, microprinting, color-shift ink) at 99.4% precision.', color: 'var(--success)' },
  { nb: 'Notebook 6', title: 'Fraud Network Graph Engine', desc: 'NetworkX graph analysis for Louvain community detection, money mule account flagging, and central actor PageRank scoring.', color: 'var(--accent-purple)' },
  { nb: 'Notebook 7', title: 'Geospatial Intelligence Engine', desc: 'DBSCAN spatial clustering, district risk ranking, peak crime window forecasting, and LEA field resource optimization.', color: 'var(--high)' },
];

const About = () => {
  const navigate = useNavigate();

  return (
    <div className="page-wrapper py-12">
      <div className="container" style={{ maxWidth: '1000px' }}>
        
        {/* Header */}
        <div className="text-center mb-10">
          <div className="hero-badge mb-3" style={{ margin: '0 auto 0.75rem' }}>
            <ShieldCheck size={16} color="var(--primary)" />
            <span>ET AI Hackathon 2026 — PS6 Architecture</span>
          </div>
          <h1 style={{ marginBottom: '0.5rem' }}>Digital Public Safety Platform</h1>
          <p className="text-muted" style={{ maxWidth: '640px', margin: '0 auto', fontSize: '1.05rem' }}>
            A next-generation AI orchestrator fusing 6 specialized Python intelligence engines into legally admissible court reports.
          </p>
        </div>

        {/* Platform Overview */}
        <div className="card mb-8 p-6" style={{ background: '#fff' }}>
          <h3 className="mb-3 text-primary">How The Orchestrator Operates</h3>
          <p className="text-slate-600 mb-4" style={{ lineHeight: '1.7' }}>
            When digital evidence is ingested (via citizen upload or police intake), the Platform Orchestrator (Notebook 8) normalizes entities, runs parallel cross-engine intelligence evaluation, fuses threat & confidence scores, and produces Section 65B certified legal packages.
          </p>

          <div className="grid md:grid-cols-2 gap-4 mt-6">
            <div className="p-4 rounded-lg bg-blue-50 border border-blue-100">
              <h4 className="text-primary mb-1">Section 65B Admissibility</h4>
              <p className="text-xs text-slate-600 mb-0">Every ingested file is hashed with SHA-256 and appended to a timestamped immutable audit ledger compliant with the Indian Evidence Act.</p>
            </div>
            <div className="p-4 rounded-lg bg-purple-50 border border-purple-100">
              <h4 className="text-purple-800 mb-1">Multi-Stakeholder Directives</h4>
              <p className="text-xs text-slate-600 mb-0">Outputs tailored action directives for Police Officers, Bank Fraud Teams, Telecom SIM Takedown teams, and Citizen Alerts.</p>
            </div>
          </div>
        </div>

        {/* Engine Grid */}
        <div className="mb-10">
          <h3 className="mb-6 text-center">The Six AI Engines</h3>
          <div className="grid md:grid-cols-2 gap-4">
            {ENGINES_INFO.map((eng, i) => (
              <div key={i} className="card p-5" style={{ borderTop: `4px solid ${eng.color}` }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 800, color: eng.color, fontFamily: "'JetBrains Mono', monospace", marginBottom: '0.25rem' }}>
                  {eng.nb}
                </div>
                <h4 className="mb-2" style={{ fontSize: '1rem', color: 'var(--text-heading)' }}>{eng.title}</h4>
                <p className="text-xs text-slate-600" style={{ lineHeight: '1.65', margin: 0 }}>{eng.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Action Call */}
        <div className="card text-center p-8" style={{ background: 'linear-gradient(135deg, var(--blue-50) 0%, #ffffff 100%)', border: '1.5px solid var(--blue-200)' }}>
          <h3 className="mb-2">Experience The Platform In Action</h3>
          <p className="text-muted text-sm mb-6">Analyze synthetic benchmark cases or submit custom evidence files.</p>
          <button className="btn btn-primary" onClick={() => navigate('/analyze')}>
            <span>Launch Evidence Intake</span>
            <ArrowRight size={16} />
          </button>
        </div>

      </div>
    </div>
  );
};

export default About;
