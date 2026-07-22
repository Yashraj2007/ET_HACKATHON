import React, { useEffect, useState, useRef } from 'react';
import { 
  CheckCircle2, Circle, Loader2, AlertCircle, Clock, ShieldCheck, 
  Cpu, Brain, Network, MapPin, Zap, ShieldAlert, Sparkles
} from 'lucide-react';
import { streamAnalysisProgress } from '../services/api';

const STAGE_CONFIGS = [
  { id: "Case Intake", title: "Case Intake & Hash Verification", desc: "Ingesting evidence payload and calculating SHA-256 custody hash", icon: <Cpu size={16} /> },
  { id: "Evidence Routing", title: "Evidence Routing Plan", desc: "Analyzing multi-modal format & routing to specialized engines", icon: <Zap size={16} /> },
  { id: "Notebook 4 - Evidence Intelligence", title: "Notebook 4 · Multi-Modal Evidence Extraction", desc: "Extracting phone numbers, UPI handles & organizations via OCR", icon: <Zap size={16} /> },
  { id: "Notebook 2 - Fraud Intelligence", title: "Notebook 2 · AI Fraud Intelligence Engine", desc: "Running RAG vector search & LLM scam classification", icon: <Brain size={16} /> },
  { id: "Notebook 5 - Counterfeit Intelligence", title: "Notebook 5 · Counterfeit Currency Detector", desc: "Verifying RBI security thread, watermark & microprinting", icon: <ShieldAlert size={16} /> },
  { id: "Notebook 6 - Fraud Network Intelligence", title: "Notebook 6 · Fraud Network Graph", desc: "Mapping NetworkX graph nodes & money mule account links", icon: <Network size={16} /> },
  { id: "Notebook 7 - Geospatial Intelligence", title: "Notebook 7 · Geospatial Risk Engine", desc: "Calculating DBSCAN crime clusters & district risk ranks", icon: <MapPin size={16} /> },
  { id: "Threat Fusion Engine", title: "Threat Fusion Engine", desc: "Fusing threat scores into multi-dimensional risk matrix", icon: <Sparkles size={16} /> },
  { id: "Notebook 3 - Decision Intelligence", title: "Notebook 3 · Decision Intelligence Directives", desc: "Generating action directives for Police, Banks, Telecom & Citizens", icon: <ShieldCheck size={16} /> }
];

const Processing = ({ taskId, caseId, onComplete }) => {
  const [completedStages, setCompletedStages] = useState({});
  const [currentStageId, setCurrentStageId] = useState(STAGE_CONFIGS[0].id);
  const [progressPercent, setProgressPercent] = useState(8);
  const [error, setError] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  const timerRef = useRef(null);

  // Stopwatch timer
  useEffect(() => {
    const start = Date.now();
    timerRef.current = setInterval(() => {
      setElapsedMs(Date.now() - start);
    }, 50);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!taskId) return;

    const unsubscribe = streamAnalysisProgress(
      taskId,
      (eventData) => {
        const { stage, duration_ms, status, percent } = eventData;
        
        setCompletedStages(prev => ({
          ...prev,
          [stage]: { duration_ms, status }
        }));
        
        if (percent) setProgressPercent(percent);

        const currentIndex = STAGE_CONFIGS.findIndex(s => s.id === stage);
        if (currentIndex !== -1 && currentIndex < STAGE_CONFIGS.length - 1) {
          setCurrentStageId(STAGE_CONFIGS[currentIndex + 1].id);
        }
      },
      (masterPackage) => {
        setProgressPercent(100);
        setTimeout(() => {
          if (timerRef.current) clearInterval(timerRef.current);
          if (onComplete) onComplete(masterPackage);
        }, 800);
      },
      (err) => {
        console.error('Processing stream error:', err);
        setError(err.message || 'Error occurred during backend execution');
      }
    );

    return () => {
      unsubscribe();
    };
  }, [taskId, onComplete]);

  return (
    <div className="card animate-fade-in" style={{ maxWidth: '720px', margin: '0 auto', padding: '2.25rem' }}>
      
      {/* Top Header */}
      <div className="text-center mb-8">
        
        {/* Animated Circular Progress Meter */}
        <div style={{ position: 'relative', width: 84, height: 84, margin: '0 auto 1.25rem' }}>
          <svg width="84" height="84" viewBox="0 0 84 84">
            <circle cx="42" cy="42" r="36" stroke="var(--border)" strokeWidth="4.5" fill="none" />
            <circle 
              cx="42" cy="42" r="36" 
              stroke="var(--primary)" 
              strokeWidth="4.5" 
              fill="none" 
              strokeDasharray="226.19"
              strokeDashoffset={226.19 - (226.19 * progressPercent) / 100}
              strokeLinecap="round"
              style={{ transition: 'stroke-dashoffset 0.35s cubic-bezier(0.16, 1, 0.3, 1)', transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}
            />
          </svg>

          <div style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexDirection: 'column'
          }}>
            <span style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-heading)', lineHeight: 1 }}>
              {progressPercent}%
            </span>
            <span style={{ fontSize: '0.62rem', color: 'var(--slate-500)', fontFamily: "'JetBrains Mono', monospace", marginTop: '0.15rem' }}>
              {(elapsedMs / 1000).toFixed(2)}s
            </span>
          </div>
        </div>

        <h2 style={{ fontSize: '1.4rem', marginBottom: '0.25rem' }}>Executing AI Intelligence Pipeline</h2>
        <p style={{ color: 'var(--slate-600)', fontSize: '0.9rem' }}>
          Fusing 6 specialized Python AI notebook engines in real-time...
        </p>

        {/* Status Bar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'var(--bg-subtle)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)', padding: '0.5rem 0.85rem',
          marginTop: '1.25rem', fontSize: '0.78rem', fontFamily: "'JetBrains Mono', monospace"
        }}>
          <span style={{ fontWeight: 700, color: 'var(--text-heading)' }}>
            CASE REF: {caseId || 'DPSP-ACTIVE'}
          </span>
          <span style={{ fontWeight: 700, color: 'var(--text-muted)' }}>
            ELAPSED: {(elapsedMs / 1000).toFixed(2)}s
          </span>
          <span style={{ fontWeight: 700, color: 'var(--success-text)', background: 'var(--success-bg)', padding: '0.15rem 0.55rem', borderRadius: 'var(--radius-full)', border: '1px solid var(--success-bd)', fontSize: '0.7rem' }}>
            ● PIPELINE LIVE
          </span>
        </div>

        {/* Progress Bar */}
        <div className="progress-bar" style={{ height: '5px', marginTop: '0.75rem' }}>
          <div 
            className="progress-fill" 
            style={{ 
              width: `${progressPercent}%`, 
              background: 'var(--primary)' 
            }} 
          />
        </div>
      </div>

      {error && (
        <div className="mb-6 p-3.5 rounded flex items-center gap-3" style={{ background: 'var(--critical-bg)', border: '1px solid var(--critical-bd)', color: 'var(--critical-text)' }}>
          <AlertCircle size={18} />
          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{error}</span>
        </div>
      )}

      {/* Clean Pipeline Steps List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
        {STAGE_CONFIGS.map((stage, idx) => {
          const stageData = completedStages[stage.id];
          const isCompleted = !!stageData;
          const isActive = currentStageId === stage.id && !isCompleted;

          return (
            <div 
              key={stage.id} 
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)',
                transition: 'var(--transition)',
                background: isActive ? 'var(--bg-subtle)' : isCompleted ? '#FFFFFF' : 'var(--bg-subtle)',
                border: isActive ? '1.5px solid var(--primary)' : isCompleted ? '1px solid var(--border)' : '1px solid var(--border)',
                opacity: isCompleted || isActive ? 1 : 0.45,
                boxShadow: isActive ? 'var(--shadow-sm)' : 'none'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '8px',
                  background: isCompleted ? 'var(--success-bg)' : isActive ? 'var(--primary)' : 'var(--slate-100)',
                  border: isCompleted ? '1px solid var(--success-bd)' : isActive ? '1px solid var(--primary)' : '1px solid var(--border)',
                  color: isCompleted ? 'var(--success-text)' : isActive ? '#FFFFFF' : 'var(--slate-500)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0
                }}>
                  {isCompleted ? <CheckCircle2 size={16} /> : isActive ? <Loader2 size={16} className="animate-spin" /> : stage.icon}
                </div>

                <div>
                  <div style={{
                    fontSize: '0.875rem', fontWeight: isActive ? 800 : isCompleted ? 700 : 500,
                    color: isActive ? 'var(--primary)' : isCompleted ? 'var(--text-heading)' : 'var(--slate-600)'
                  }}>
                    {stage.title}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)', marginTop: '0.1rem' }}>
                    {isActive ? (
                      <span style={{ fontWeight: 600, color: 'var(--primary)' }}>● Active now — {stage.desc}</span>
                    ) : (
                      stage.desc
                    )}
                  </div>
                </div>
              </div>

              {stageData && stageData.duration_ms !== undefined && (
                <div style={{
                  display: 'flex', alignItems: 'center', gap: '0.3rem',
                  fontSize: '0.75rem', color: 'var(--slate-500)',
                  fontFamily: "'JetBrains Mono', monospace",
                  background: 'var(--bg-subtle)', padding: '0.2rem 0.5rem',
                  borderRadius: '4px', border: '1px solid var(--border)'
                }}>
                  <Clock size={11} />
                  <span>{stageData.duration_ms} ms</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Processing;
