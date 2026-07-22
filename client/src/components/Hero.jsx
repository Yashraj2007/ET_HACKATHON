import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Brain, Network, MapPin, Zap, ShieldAlert, Award, Sparkles } from 'lucide-react';

const STATS = [
  { value: '99.4%', label: 'Counterfeit Accuracy', sub: 'Multi-denomination RBI' },
  { value: '98.2%', label: 'Digital Arrest Precision', sub: 'Vector RAG Engine' },
  { value: '<0.08%', label: 'False Positive Rate', sub: 'Cross-notebook verified' },
  { value: '14 Days', label: 'Network Lead Time', sub: 'Early link detection' },
];

const ENGINES = [
  { nb: 'NB-2', name: 'Fraud Intel',     icon: <Brain size={15} /> },
  { nb: 'NB-3', name: 'Decision Engine', icon: <ShieldAlert size={15} /> },
  { nb: 'NB-4', name: 'Evidence OCR',    icon: <Zap size={15} /> },
  { nb: 'NB-5', name: 'Counterfeit',     icon: <ShieldAlert size={15} /> },
  { nb: 'NB-6', name: 'Network Graph',   icon: <Network size={15} /> },
  { nb: 'NB-7', name: 'Geospatial',      icon: <MapPin size={15} /> },
];

const Hero = () => {
  const navigate = useNavigate();

  return (
    <section style={{ padding: '3.5rem 0 2.5rem' }}>
      <div className="container">

        {/* Hero Headline Box */}
        <div style={{ maxWidth: 780, margin: '0 auto', textAlign: 'center', marginBottom: '3rem' }}>
          
          {/* ET AI Hackathon 2026 Badge */}
          <div className="hero-tag">
            <Award size={14} color="var(--primary)" />
            <span>ET AI Hackathon 2026 · Problem Statement 6 (PS6) · All 6 AI Engines Live</span>
          </div>

          <h1 style={{ marginBottom: '1.25rem', lineHeight: 1.15 }}>
            National Digital Public Safety & <br />
            <span className="text-gradient">Crime Intelligence Platform</span>
          </h1>

          <p style={{ fontSize: '1.05rem', color: 'var(--slate-600)', lineHeight: 1.65, marginBottom: '2rem', maxWidth: 660, margin: '0 auto 2rem' }}>
            Built for <strong>ET AI Hackathon 2026</strong>. Upload digital evidence — text, audio, images, PDFs — and 6 AI engines fuse real-time threat scores, fraud network graphs, and geospatial intelligence into one legally admissible package.
          </p>

          <div style={{ display: 'flex', gap: '0.85rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button className="btn btn-primary btn-lg" onClick={() => navigate('/analyze')}>
              <span>Start Intelligence Analysis</span>
              <ArrowRight size={16} />
            </button>
            <button className="btn btn-outline btn-lg" onClick={() => navigate('/reports')}>
              <span>View Case Archives</span>
            </button>
          </div>
        </div>

        {/* Clean Stats Bar */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem', marginBottom: '1.75rem'
        }}>
          {STATS.map((s, i) => (
            <div key={i} className="card" style={{ textAlign: 'center', padding: '1.25rem' }}>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-heading)', letterSpacing: '-0.03em', lineHeight: 1, marginBottom: '0.35rem' }}>
                {s.value}
              </div>
              <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--slate-800)', marginBottom: '0.15rem' }}>
                {s.label}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--slate-500)' }}>
                {s.sub}
              </div>
            </div>
          ))}
        </div>

        {/* Engine Status Grid */}
        <div className="card" style={{ padding: '1.25rem 1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="status-dot" />
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-heading)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                ET AI HACKATHON 2026 — ACTIVE ARCHITECTURE
              </span>
            </div>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
              digital_public_safety_platform.py (Notebook 8 Rev 4)
            </span>
          </div>

          <div className="grid md:grid-cols-6 gap-2">
            {ENGINES.map((eng, i) => (
              <div key={i} style={{ padding: '0.6rem', borderRadius: 'var(--radius-sm)', background: 'var(--bg-subtle)', border: '1px solid var(--border)', textAlign: 'center' }}>
                <div style={{ color: 'var(--primary)', display: 'flex', justifyContent: 'center', marginBottom: '0.2rem' }}>{eng.icon}</div>
                <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-heading)' }}>{eng.nb}</div>
                <div style={{ fontSize: '0.68rem', color: 'var(--slate-600)' }}>{eng.name}</div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </section>
  );
};

export default Hero;
