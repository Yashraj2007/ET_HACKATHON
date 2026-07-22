import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Dashboard from '../components/Dashboard';
import ReportViewer from '../components/ReportViewer';
import { fetchCasesArchive, fetchCaseDetails } from '../services/api';
import { ShieldAlert, ArrowLeft, RefreshCw } from 'lucide-react';

const DashboardPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [master, setMaster] = useState(location.state?.caseData || null);
  const [loading, setLoading] = useState(!location.state?.caseData);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!master) {
      fetchCasesArchive()
        .then(async (cases) => {
          if (cases && cases.length > 0) {
            const latestCaseId = cases[cases.length - 1].case_id;
            const fullPkg = await fetchCaseDetails(latestCaseId);
            setMaster(fullPkg);
          } else {
            setError('No processed cases found. Please submit evidence to analyze a case first.');
          }
        })
        .catch(err => {
          console.error(err);
          setError('Could not load case data from intelligence backend.');
        })
        .finally(() => setLoading(false));
    }
  }, [master]);

  const caseId = master?.case?.case_id || master?.package_id || 'CASE-ACTIVE';
  const decision = master?.decision_intelligence?.case_decision || master?.decision_intelligence?.decision_category || 'Action Required';

  return (
    <div className="container py-8">
      {loading ? (
        <div className="card text-center py-16" style={{ background: '#fff' }}>
          <div className="animate-spin mb-4" style={{ display: 'inline-block' }}>
            <RefreshCw size={36} color="var(--primary)" />
          </div>
          <h3>Loading Master Intelligence Package...</h3>
          <p className="text-muted text-sm mt-1">Retrieving cross-engine fusion results for {caseId}</p>
        </div>
      ) : error ? (
        <div className="card text-center py-16" style={{ background: '#fff' }}>
          <ShieldAlert size={48} color="var(--warning)" style={{ margin: '0 auto 1rem' }} />
          <h3 className="mb-2">{error}</h3>
          <p className="text-muted mb-6">Start by uploading multi-modal evidence or selecting a benchmark scenario.</p>
          <button className="btn btn-primary" onClick={() => navigate('/analyze')}>
            Go to Submit Evidence
          </button>
        </div>
      ) : (
        <div className="animate-fade-in flex flex-col gap-8">
          
          {/* Header Action Bar */}
          <div className="flex items-center justify-between flex-wrap gap-4 pb-4 border-b">
            <div>
              <div className="section-label mb-1">Intelligence Package Dashboard</div>
              <h1 style={{ fontSize: '1.875rem', marginBottom: '0.2rem' }}>Master Analysis Package</h1>
              <p className="text-muted text-sm" style={{ margin: 0 }}>
                Case Identifier: <strong className="font-mono" style={{ color: 'var(--text-heading)' }}>{caseId}</strong>
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button className="btn btn-outline btn-sm" onClick={() => navigate('/analyze')}>
                <ArrowLeft size={15} /> Analyze New Case
              </button>
              <div className="badge badge-high" style={{ fontSize: '0.875rem', padding: '0.45rem 1rem' }}>
                {decision}
              </div>
            </div>
          </div>
          
          {/* Dashboard Component */}
          <Dashboard master={master} />
          
          {/* Report Viewer Component */}
          <div className="mt-6">
            <ReportViewer master={master} />
          </div>
        </div>
      )}
    </div>
  );
};

export default DashboardPage;
