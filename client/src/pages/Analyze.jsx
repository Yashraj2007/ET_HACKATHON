import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import CaseIntake from '../components/CaseIntake';
import Processing from '../components/Processing';

const Analyze = () => {
  const [isProcessing, setIsProcessing] = useState(false);
  const [activeTask, setActiveTask] = useState({ taskId: null, caseId: null });
  const navigate = useNavigate();

  const handleProcessStart = ({ taskId, caseId }) => {
    setActiveTask({ taskId, caseId });
    setIsProcessing(true);
  };

  const handleProcessComplete = (masterPackage) => {
    // Navigate to dashboard and pass the real master intelligence result in state
    navigate('/dashboard', { state: { caseData: masterPackage } });
  };

  return (
    <div className="container py-12">
      {!isProcessing ? (
        <CaseIntake onProcessStart={handleProcessStart} />
      ) : (
        <Processing 
          taskId={activeTask.taskId} 
          caseId={activeTask.caseId} 
          onComplete={handleProcessComplete} 
        />
      )}
    </div>
  );
};

export default Analyze;
