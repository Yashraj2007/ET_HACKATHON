// API Service for interacting with FastAPI Intelligence Engine Backend

export const submitEvidence = async (formData) => {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    throw new Error(`Server returned error ${response.status}: ${await response.text()}`);
  }
  return await response.json();
};

export const streamAnalysisProgress = (taskId, onProgress, onComplete, onError) => {
  const eventSource = new EventSource(`/api/analyze/stream/${taskId}`);

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'progress') {
        if (onProgress) onProgress(data);
      } else if (data.type === 'complete') {
        if (onComplete) onComplete(data.result);
        eventSource.close();
      } else if (data.type === 'error') {
        if (onError) onError(new Error(data.error || 'Pipeline error'));
        eventSource.close();
      }
    } catch (err) {
      if (onError) onError(err);
      eventSource.close();
    }
  };

  eventSource.onerror = (err) => {
    console.error('SSE Error:', err);
    if (onError) onError(err);
    eventSource.close();
  };

  return () => {
    eventSource.close();
  };
};

export const fetchCaseDetails = async (caseId) => {
  const response = await fetch(`/api/case/${caseId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch case: ${response.statusText}`);
  }
  return await response.json();
};

export const fetchCasesArchive = async () => {
  const response = await fetch('/api/cases');
  if (!response.ok) {
    throw new Error(`Failed to fetch cases list: ${response.statusText}`);
  }
  return await response.json();
};

export const getReportDownloadUrl  = (caseId) => `/api/case/${encodeURIComponent(caseId)}/report`;
export const getReportHtmlUrl      = (caseId) => `/api/case/${encodeURIComponent(caseId)}/download/html`;
export const getReportJsonUrl      = (caseId) => `/api/case/${encodeURIComponent(caseId)}/download/json`;

/** Trigger a real file download by temporarily creating a hidden <a> element. */
export const triggerFileDownload = (url) => {
  const a = document.createElement('a');
  a.href = url;
  a.setAttribute('download', '');
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
};
