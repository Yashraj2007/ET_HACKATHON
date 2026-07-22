import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, Image as ImageIcon, Mic, Video, Smartphone, Zap, CheckCircle2, AlertCircle, ShieldAlert, Sparkles, Check } from 'lucide-react';
import { submitEvidence } from '../services/api';

const SYNTHETIC_BENCHMARKS = [
  {
    case_id: "DPSP-CASE-001",
    name: "Digital Arrest Scam",
    code: "DPSP-CASE-001",
    badge: "91.6% Threat",
    badgeType: "badge-critical",
    city: "Kolhapur",
    state: "Maharashtra",
    amount: 50000,
    isCurrency: false,
    text: "Caller claimed to be from CBI and RBI, said there is an arrest warrant against me, demanded a video call and payment via UPI to rahul@okaxis to avoid digital arrest. Caller phone number was 9876543210.",
  },
  {
    case_id: "DPSP-CASE-002",
    name: "Linked Network Ring",
    code: "DPSP-CASE-002",
    badge: "91.8% Threat",
    badgeType: "badge-critical",
    city: "Kolhapur",
    state: "Maharashtra",
    amount: 55000,
    isCurrency: false,
    text: "Received threatening calls from CBI impersonator 9876543210. Demanded immediate payment to rahul@okaxis claiming my bank account is implicated in national money laundering ring.",
  },
  {
    case_id: "DPSP-CASE-003",
    name: "Digital Arrest Scam Call",
    code: "DPSP-CASE-003",
    badge: "73.2% Threat",
    badgeType: "badge-high",
    city: "Pune",
    state: "Maharashtra",
    amount: 60000,
    isCurrency: false,
    text: "CBI officer Vijay Sharma called from 9876543210 demanding urgent video call compliance and transfer to rahul@okaxis.",
  },
  {
    case_id: "DPSP-CASE-CURRENCY-001",
    name: "Counterfeit Currency Note",
    code: "CURRENCY-001",
    badge: "21.6% Review",
    badgeType: "badge-warning",
    city: "Mumbai",
    state: "Maharashtra",
    amount: 500,
    isCurrency: true,
    text: "I received this 500 rupee note as change and it feels off. Security thread missing, watermark misaligned.",
  },
  {
    case_id: "DPSP-CASE-LOWSIGNAL-001",
    name: "Low-Signal UPI Query",
    code: "LOWSIGNAL-001",
    badge: "35.0% Awareness",
    badgeType: "badge-safe",
    city: "Mumbai",
    state: "Maharashtra",
    amount: 1000,
    isCurrency: false,
    text: "This is urgent, please call me back as soon as you can, it's important regarding upi transaction.",
  }
];

const CaseIntake = ({ onProcessStart }) => {
  const [files, setFiles] = useState([]);
  const [content, setContent] = useState('');
  const [citizenName, setCitizenName] = useState('');
  const [city, setCity] = useState('Mumbai');
  const [state, setState] = useState('Maharashtra');
  const [amount, setAmount] = useState('');
  const [isCurrency, setIsCurrency] = useState(false);
  const [priority, setPriority] = useState('Normal');
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedCaseId, setSelectedCaseId] = useState('');

  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(Array.from(e.target.files));
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };
  
  const handleDragLeave = () => {
    setIsDragging(false);
  };
  
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handlePresetSelect = (preset) => {
    setSelectedCaseId(preset.case_id);
    setCity(preset.city);
    setState(preset.state);
    setAmount(preset.amount);
    setIsCurrency(preset.isCurrency);
    setContent(preset.text);
    setCitizenName("Verified Citizen Intake");
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      if (selectedCaseId) {
        formData.append('case_id', selectedCaseId);
      }
      formData.append('content', content);
      formData.append('citizen_name', citizenName || 'Anonymous Citizen');
      formData.append('city', city || 'Mumbai');
      formData.append('state', state || 'Maharashtra');
      formData.append('priority', priority);
      formData.append('amount_involved', amount ? parseFloat(amount) : 0.0);
      formData.append('is_currency', isCurrency ? 'true' : 'false');

      if (files && files.length > 0) {
        files.forEach(file => formData.append('files', file));
      }

      const res = await submitEvidence(formData);
      if (onProcessStart) {
        onProcessStart({ taskId: res.task_id, caseId: res.case_id });
      }
    } catch (err) {
      console.error(err);
      setError(err.message || 'Failed to submit evidence to backend python engines');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card" style={{ maxWidth: '960px', margin: '0 auto', padding: '2.25rem' }}>
      
      {/* Header */}
      <div className="text-center mb-8">
        <span className="hero-tag">
          <Zap size={14} />
          Multi-Modal Intelligence Ingestion
        </span>
        <h2>Evidence Intake Portal</h2>
        <p className="text-muted text-sm mt-2" style={{ maxWidth: '620px', margin: '0.5rem auto 0' }}>
          Upload digital evidence (PDFs, Images, Audio, Screenshots) or select an official benchmark dataset for instant threat fusion.
        </p>
      </div>

      {/* Benchmark Presets Section */}
      <div style={{
        marginBottom: '2rem', padding: '1.25rem',
        borderRadius: 'var(--radius-lg)', background: 'var(--bg-subtle)',
        border: '1px solid var(--border)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: 'var(--slate-800)', fontWeight: 800, fontSize: '0.85rem' }}>
            <Zap size={16} color="var(--primary)" />
            <span>Official Notebook 8 Benchmark Scenarios</span>
          </div>
          <span style={{ fontSize: '0.72rem', color: 'var(--slate-500)', fontWeight: 600 }}>Click to Load Preset</span>
        </div>

        {/* Clean Responsive Card Grid */}
        <div className="grid md:grid-cols-3 gap-3">
          {SYNTHETIC_BENCHMARKS.map((preset, idx) => {
            const isSelected = selectedCaseId === preset.case_id;
            return (
              <div
                key={idx}
                className="card card-interactive"
                onClick={() => handlePresetSelect(preset)}
                style={{
                  display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                  padding: '1rem', borderRadius: 'var(--radius)',
                  background: isSelected ? 'var(--primary-light)' : '#FFFFFF',
                  borderColor: isSelected ? 'var(--primary)' : 'var(--border)',
                  boxShadow: isSelected ? '0 4px 14px rgba(37, 99, 235, 0.15)' : 'var(--shadow-xs)',
                  position: 'relative'
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <span style={{ fontSize: '0.68rem', fontFamily: "'JetBrains Mono', monospace", color: 'var(--slate-500)', fontWeight: 600 }}>
                      {preset.code}
                    </span>
                    {isSelected && <Check size={14} color="var(--primary)" strokeWidth={3} />}
                  </div>

                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-heading)', marginBottom: '0.5rem' }}>
                    {preset.name}
                  </div>
                </div>

                <div style={{ marginTop: '0.5rem' }}>
                  <span className={`badge ${preset.badgeType}`}>
                    {preset.badge}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 rounded-lg flex items-center gap-3" style={{ background: 'var(--critical-bg)', border: '1px solid var(--critical-bd)', color: 'var(--critical-text)' }}>
          <AlertCircle size={18} />
          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{error}</span>
        </div>
      )}

      {/* Main Intake Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        
        {/* Drag & Drop File Zone */}
        <div 
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          style={{
            border: `2px dashed ${isDragging ? 'var(--primary)' : 'var(--border-hover)'}`,
            backgroundColor: isDragging ? 'var(--primary-light)' : 'var(--bg-subtle)',
            borderRadius: 'var(--radius-lg)',
            padding: '2.25rem 1.5rem',
            textAlign: 'center',
            transition: 'var(--transition)',
            cursor: 'pointer'
          }}
        >
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            multiple 
            style={{ display: 'none' }} 
            accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.txt"
          />
          
          <div style={{
            width: 48, height: 48, borderRadius: '12px', background: '#FFFFFF',
            border: '1px solid var(--border)', display: 'flex', alignItems: 'center',
            justifyContent: 'center', margin: '0 auto 0.85rem', color: 'var(--primary)',
            boxShadow: 'var(--shadow-xs)'
          }}>
            <UploadCloud size={24} />
          </div>

          <h3 style={{ marginBottom: '0.25rem', fontSize: '1rem' }}>
            {files.length > 0 ? `${files.length} File(s) Selected` : 'Click or Drag Evidence Files Here'}
          </h3>
          <p className="text-muted text-xs mb-4">
            {files.length > 0 ? files.map(f => f.name).join(', ') : 'Supports PDF reports, OCR Images, Audio Transcripts, and Video evidence'}
          </p>

          <div className="flex justify-center gap-3 flex-wrap">
            {[
              { icon: <FileText size={14} />, label: 'Documents' },
              { icon: <ImageIcon size={14} />, label: 'Images' },
              { icon: <Mic size={14} />, label: 'Audio' },
              { icon: <Video size={14} />, label: 'Video' },
              { icon: <Smartphone size={14} />, label: 'Screenshots' },
            ].map((item, idx) => (
              <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--slate-600)', background: '#FFFFFF', padding: '0.3rem 0.6rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
                {item.icon}
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Text Evidence Input */}
        <div>
          <label className="form-label">
            Case Text / Call Transcript / Extracted Statements
          </label>
          <textarea
            rows={4}
            className="form-textarea"
            placeholder="Paste scam messages, phone numbers (+91...), UPI IDs (name@okaxis), bank account details, or victim statements..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
        </div>

        {/* Form Controls Grid */}
        <div className="grid md:grid-cols-3 gap-4">
          <div>
            <label className="form-label">Citizen / Complainant</label>
            <input 
              type="text" 
              className="form-input"
              placeholder="e.g. Ramesh Kumar"
              value={citizenName}
              onChange={(e) => setCitizenName(e.target.value)}
            />
          </div>

          <div>
            <label className="form-label">City Location</label>
            <input 
              type="text" 
              className="form-input"
              placeholder="e.g. Mumbai"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </div>

          <div>
            <label className="form-label">State Jurisdiction</label>
            <input 
              type="text" 
              className="form-input"
              placeholder="e.g. Maharashtra"
              value={state}
              onChange={(e) => setState(e.target.value)}
            />
          </div>

          <div>
            <label className="form-label">Amount Involved (INR ₹)</label>
            <input 
              type="number" 
              className="form-input"
              placeholder="e.g. 50000"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>

          <div>
            <label className="form-label">Priority Assessment</label>
            <select 
              className="form-select"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="Normal">Normal Priority</option>
              <option value="High">High Urgency</option>
              <option value="Emergency">Emergency Threat</option>
            </select>
          </div>

          <div className="flex items-center" style={{ marginTop: '1.4rem' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-heading)' }}>
              <input 
                type="checkbox" 
                checked={isCurrency}
                onChange={(e) => setIsCurrency(e.target.checked)}
                style={{ width: '16px', height: '16px', accentColor: 'var(--primary)', cursor: 'pointer' }}
              />
              <span>Currency Note Image (Triggers NB-5)</span>
            </label>
          </div>
        </div>

        {/* Submit Action Button */}
        <div className="flex justify-center mt-3">
          <button 
            type="submit" 
            className="btn btn-primary btn-lg"
            style={{ minWidth: '280px' }}
            disabled={loading}
          >
            {loading ? (
              <span>Executing Intelligence Pipeline...</span>
            ) : (
              <>
                <CheckCircle2 size={18} />
                <span>Run Real-Time AI Analysis</span>
              </>
            )}
          </button>
        </div>

      </form>
    </div>
  );
};

export default CaseIntake;
