import React from 'react';
import Hero from '../components/Hero';
import { FileSearch, Network, ShieldAlert, MapPin, Cpu, Lock, ArrowRight, CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const FEATURES = [
  {
    icon: <FileSearch size={20} color="var(--primary)" />,
    tag: 'NB-4',
    title: 'Multi-Modal Evidence Ingestion',
    desc: 'OCR, audio transcription, image analysis, and entity extraction from any evidence format — text, PDF, image, audio, video — in seconds.',
    points: ['SHA-256 integrity hash verification', 'Automated language detection', 'Cross-evidence entity deduplication'],
  },
  {
    icon: <Network size={20} color="var(--primary)" />,
    tag: 'NB-6',
    title: 'Fraud Network Graph Engine',
    desc: 'NetworkX-powered graph connects cases via shared phone numbers, UPI IDs, organizations, and victim patterns across jurisdictions.',
    points: ['Louvain community detection', 'Money mule account flagging', 'PageRank central actor scoring'],
  },
  {
    icon: <ShieldAlert size={20} color="var(--primary)" />,
    tag: 'NB-2',
    title: 'AI Fraud Intelligence Engine',
    desc: 'RAG-backed LLM classification delivers explainable fraud type, risk score, and validated indicators — zero black-box decisions.',
    points: ['8 fraud taxonomy categories', 'Hybrid keyword + vector search', 'LLM reasoning chain with fallback'],
  },
  {
    icon: <MapPin size={20} color="var(--primary)" />,
    tag: 'NB-7',
    title: 'Geospatial Crime Hotspots',
    desc: 'Hotspot detection, district risk ranking, campaign spread analysis, and resource recommendations for field deployment.',
    points: ['DBSCAN spatial clustering', 'Predictive district risk ranking', 'Peak day/time intelligence'],
  },
  {
    icon: <Cpu size={20} color="var(--primary)" />,
    tag: 'NB-5',
    title: 'Counterfeit Currency Detector',
    desc: 'Multi-denomination RBI watermark, security thread, microprinting, and color-shift ink verification from uploaded images.',
    points: ['99.4% multi-denomination accuracy', 'RBI feature verification checklist', 'Serial number anomaly detection'],
  },
  {
    icon: <Lock size={20} color="var(--primary)" />,
    tag: 'NB-8',
    title: 'Legal Admissibility & Audit Chain',
    desc: 'Full chain-of-custody: SHA-256 hashed evidence, timestamped audit trail, Section 65B certification, and ReportLab PDF generation.',
    points: ['Section 65B Indian Evidence Act', 'Timestamped SHA-256 custody trail', 'Multi-stakeholder PDF packages'],
  },
];

const Home = () => {
  const navigate = useNavigate();

  return (
    <div>
      <Hero />

      {/* Features Section */}
      <section style={{ padding: '3.5rem 0', background: 'var(--bg-main)' }}>
        <div className="container">
          <div style={{ textAlign: 'center', marginBottom: '2.5rem' }}>
            <div className="section-label" style={{ marginBottom: '0.4rem' }}>Platform Capabilities</div>
            <h2 style={{ marginBottom: '0.5rem' }}>Six AI Engines. One Unified Architecture.</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem', maxWidth: 540, margin: '0 auto' }}>
              Every case runs through a multi-layer pipeline — converting raw evidence into actionable, legally admissible court intelligence.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            {FEATURES.map((f, i) => (
              <div key={i} className="card flex flex-col justify-between" style={{ gap: '0.85rem' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <div style={{ width: 38, height: 38, borderRadius: 8, background: 'var(--primary-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {f.icon}
                    </div>
                    <span className="badge badge-blue font-mono">
                      {f.tag}
                    </span>
                  </div>
                  <h3 style={{ fontSize: '0.98rem', marginBottom: '0.35rem' }}>{f.title}</h3>
                  <p style={{ color: 'var(--slate-600)', fontSize: '0.85rem', lineHeight: 1.6 }}>{f.desc}</p>
                </div>

                <ul style={{ listStyle: 'none', padding: 0, display: 'flex', flexDirection: 'column', gap: '0.35rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border)' }}>
                  {f.points.map((p, j) => (
                    <li key={j} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem', color: 'var(--text-body)' }}>
                      <CheckCircle2 size={13} color="var(--primary)" style={{ flexShrink: 0 }} />
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Evaluation Performance Section */}
      <section style={{ padding: '3.5rem 0', background: '#FFFFFF', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div className="container">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1.5rem', marginBottom: '2rem' }}>
            <div>
              <div className="section-label" style={{ marginBottom: '0.3rem' }}>ET AI Hackathon 2026 — PS6 Architecture</div>
              <h2 style={{ fontSize: '1.5rem', marginBottom: 0 }}>Evaluation Criteria Performance</h2>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
              {[
                { label: 'Innovation',      pct: '25%' },
                { label: 'Business Impact', pct: '25%' },
                { label: 'Technical Depth', pct: '20%' },
                { label: 'Scalability',     pct: '15%' },
                { label: 'UI/UX Polish',    pct: '15%+'},
              ].map((c, i) => (
                <div key={i} style={{ textAlign: 'center', background: 'var(--bg-subtle)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', padding: '0.75rem 1rem', minWidth: 95 }}>
                  <div style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--primary)', letterSpacing: '-0.03em', lineHeight: 1 }}>{c.pct}</div>
                  <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginTop: '0.25rem' }}>{c.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid md:grid-cols-5 gap-3">
            {[
              { label: 'Evidence Extraction', value: 'Notebook 4', sub: 'OCR & Multi-Modal Ingestion' },
              { label: 'Fraud Intelligence',   value: 'Notebook 2', sub: 'RAG Vector Search & LLM' },
              { label: 'Network Analysis',     value: 'Notebook 6', sub: 'Graph Early Link Detection' },
              { label: 'Geospatial Intelligence',value: 'Notebook 7', sub: 'Hotspot & District Risk' },
              { label: 'Decision Engine',      value: 'Notebook 3', sub: 'Action Directives & 65B Audit' },
            ].map((m, i) => (
              <div key={i} className="card text-center" style={{ padding: '1rem' }}>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--primary)', marginBottom: '0.15rem' }}>{m.value}</div>
                <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-heading)', marginBottom: '0.2rem' }}>{m.label}</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{m.sub}</div>
              </div>
            ))}
          </div>

          {/* Action CTA Banner */}
          <div style={{
            marginTop: '2.5rem', padding: '1.75rem 2rem', borderRadius: 'var(--radius)',
            background: 'var(--primary)', color: '#FFFFFF', display: 'flex',
            alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1.25rem'
          }}>
            <div>
              <h3 style={{ color: '#FFFFFF', fontSize: '1.25rem', marginBottom: '0.25rem' }}>Ready to Analyze Evidence?</h3>
              <p style={{ color: 'rgba(255, 255, 255, 0.85)', fontSize: '0.875rem', margin: 0 }}>
                Select a synthetic benchmark scenario or upload custom evidence files.
              </p>
            </div>
            <button className="btn btn-outline" style={{ background: '#FFFFFF', color: 'var(--primary)', fontWeight: 700 }} onClick={() => navigate('/analyze')}>
              <span>Launch Evidence Intake</span>
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};

export default Home;
