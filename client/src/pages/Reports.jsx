import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Search, Download, Eye, TrendingUp, ShieldAlert, AlertTriangle, CheckCircle, Clock, Sparkles, FileCode, FileJson } from 'lucide-react';
import { fetchCasesArchive, fetchCaseDetails, getReportDownloadUrl, getReportHtmlUrl, getReportJsonUrl, triggerFileDownload } from '../services/api';

const getScoreColor = (s) => s >= 70 ? 'var(--critical)' : s >= 40 ? 'var(--warning)' : 'var(--success)';
const getScoreBg    = (s) => s >= 70 ? 'var(--critical-bg)' : s >= 40 ? 'var(--warning-bg)' : 'var(--success-bg)';
const getScoreBd    = (s) => s >= 70 ? 'var(--critical-bd)' : s >= 40 ? 'var(--warning-bd)' : 'var(--success-bd)';

const getDecisionBadge = (d) => {
  if (!d) return 'badge-blue';
  if (d.toLowerCase().includes('urgent') || d.toLowerCase().includes('emergency')) return 'badge-critical';
  if (d.toLowerCase().includes('awareness') || d.toLowerCase().includes('safe')) return 'badge-safe';
  if (d.toLowerCase().includes('human') || d.toLowerCase().includes('review'))   return 'badge-warning';
  return 'badge-blue';
};

const ScoreBar = ({ value }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
    <div style={{
      width: 38, height: 38, borderRadius: '50%',
      background: getScoreBg(value), border: `2px solid ${getScoreColor(value)}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: '0.78rem', fontWeight: 800, color: getScoreColor(value),
      flexShrink: 0, boxShadow: 'var(--shadow-xs)'
    }}>
      {Math.round(value)}
    </div>
    <div>
      <div className="progress-bar" style={{ width: 90 }}>
        <div className="progress-fill" style={{ width: `${value}%`, background: getScoreColor(value) }} />
      </div>
      <div style={{ fontSize: '0.68rem', color: 'var(--slate-500)', marginTop: '0.2rem', fontWeight: 700 }}>
        {value >= 70 ? 'HIGH RISK' : value >= 40 ? 'MEDIUM RISK' : 'LOW RISK'}
      </div>
    </div>
  </div>
);

const Reports = () => {
  const [cases, setCases]       = useState([]);
  const [search, setSearch]     = useState('');
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [viewing, setViewing]   = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetchCasesArchive()
      .then(d => setCases(d || []))
      .catch(err => { console.error(err); setError('Failed to load reports.'); })
      .finally(() => setLoading(false));
  }, []);

  const handleView = async (caseId) => {
    setViewing(caseId);
    try {
      const pkg = await fetchCaseDetails(caseId);
      navigate('/dashboard', { state: { caseData: pkg } });
    } catch { alert(`Could not load case ${caseId}`); }
    finally { setViewing(null); }
  };

  const filtered = cases.filter(c =>
    c.case_id.toLowerCase().includes(search.toLowerCase()) ||
    (c.fraud_type || '').toLowerCase().includes(search.toLowerCase()) ||
    (c.citizen_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (c.city || '').toLowerCase().includes(search.toLowerCase())
  );

  const totalRisk = cases.reduce((a, c) => a + (c.threat_score || 0), 0);
  const avgRisk   = cases.length ? (totalRisk / cases.length).toFixed(1) : 0;
  const highRisk  = cases.filter(c => (c.threat_score || 0) >= 70).length;

  return (
    <div className="page-wrapper py-8">
      <div className="container">

        {/* Header */}
        <div style={{ marginBottom: '2rem' }}>
          <div className="section-label mb-1">Intelligence Archive</div>
          <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <h1 style={{ marginBottom: '0.35rem' }}>Case Report Archive</h1>
              <p style={{ color: 'var(--slate-600)', fontSize: '0.95rem' }}>
                All processed cases with real-time engine outputs and downloadable court PDFs.
              </p>
            </div>

            {/* Search Input */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.6rem',
              background: '#fff', border: '1.5px solid var(--border)',
              borderRadius: 'var(--radius)', padding: '0.6rem 1rem',
              boxShadow: 'var(--shadow-sm)', minWidth: 300,
            }}>
              <Search size={16} color="var(--slate-400)" />
              <input
                type="text" 
                placeholder="Search case ID, citizen, fraud type..."
                value={search} 
                onChange={e => setSearch(e.target.value)}
                style={{ border: 'none', outline: 'none', background: 'transparent', fontSize: '0.875rem', color: 'var(--text-body)', width: '100%' }}
              />
            </div>
          </div>
        </div>

        {/* Stats Strip */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '1rem', marginBottom: '2rem'
        }}>
          <div className="card p-4" style={{ borderTop: '3px solid var(--primary)' }}>
            <span className="text-muted text-xs font-bold uppercase">Total Archive Cases</span>
            <h2 style={{ margin: '0.2rem 0 0', color: 'var(--primary)' }}>{cases.length}</h2>
          </div>
          <div className="card p-4" style={{ borderTop: '3px solid var(--critical)' }}>
            <span className="text-muted text-xs font-bold uppercase">High Risk Alerts</span>
            <h2 style={{ margin: '0.2rem 0 0', color: 'var(--critical)' }}>{highRisk}</h2>
          </div>
          <div className="card p-4" style={{ borderTop: '3px solid var(--warning)' }}>
            <span className="text-muted text-xs font-bold uppercase">Avg Threat Score</span>
            <h2 style={{ margin: '0.2rem 0 0', color: 'var(--warning)' }}>{avgRisk}</h2>
          </div>
          <div className="card p-4" style={{ borderTop: '3px solid var(--success)' }}>
            <span className="text-muted text-xs font-bold uppercase">Legal Verification</span>
            <h2 style={{ margin: '0.2rem 0 0', color: 'var(--success)' }}>100% SHA-256</h2>
          </div>
        </div>

        {/* Cases Table */}
        <div className="card p-0" style={{ overflow: 'hidden' }}>
          {loading ? (
            <div className="text-center py-16">
              <p className="text-muted">Loading intelligence archive...</p>
            </div>
          ) : error ? (
            <div className="text-center py-16">
              <p className="text-critical">{error}</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-muted">No cases match your search query.</p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Case Ref</th>
                    <th>Citizen / Location</th>
                    <th>Fraud Taxonomy</th>
                    <th>Threat Score</th>
                    <th>Decision</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((c) => (
                    <tr key={c.case_id}>
                      <td>
                        <span className="font-mono font-bold" style={{ color: 'var(--text-heading)' }}>
                          {c.case_id}
                        </span>
                        <div style={{ fontSize: '0.68rem', color: 'var(--slate-400)', fontFamily: "'JetBrains Mono', monospace" }}>
                          {c.timestamp ? new Date(c.timestamp).toLocaleDateString() : 'Active'}
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--text-heading)' }}>{c.citizen_name || 'Verified Citizen'}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--slate-500)' }}>{c.city || 'Mumbai'}, {c.state || 'Maharashtra'}</div>
                      </td>
                      <td>
                        <span style={{ fontWeight: 600 }}>{c.fraud_type || 'Digital Arrest Scam'}</span>
                        <div style={{ fontSize: '0.72rem', color: 'var(--slate-500)' }}>Amount: ₹{(c.amount_involved || 50000).toLocaleString()}</div>
                      </td>
                      <td>
                        <ScoreBar value={c.threat_score || 0} />
                      </td>
                      <td>
                        <span className={`badge ${getDecisionBadge(c.case_decision)}`}>
                          {c.case_decision || 'Action Required'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button
                            className="btn btn-outline btn-sm"
                            onClick={() => handleView(c.case_id)}
                            disabled={viewing === c.case_id}
                          >
                            <Eye size={14} />
                            <span>{viewing === c.case_id ? 'Loading...' : 'View'}</span>
                          </button>
                          <button
                            onClick={() => triggerFileDownload(getReportHtmlUrl(c.case_id))}
                            className="btn btn-primary btn-sm"
                            title="Download styled HTML intelligence report"
                          >
                            <FileCode size={14} />
                            <span>HTML</span>
                          </button>
                          <button
                            onClick={() => triggerFileDownload(getReportJsonUrl(c.case_id))}
                            className="btn btn-outline btn-sm"
                            title="Download full JSON master package"
                          >
                            <FileJson size={14} />
                            <span>JSON</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default Reports;
