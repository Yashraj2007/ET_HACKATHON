import React from 'react';

const Footer = () => {
  return (
    <footer style={{ 
      padding: '1rem 0', 
      marginTop: 'auto', 
      opacity: 0.4, 
      borderTop: '1px solid var(--border-light)' 
    }}>
      <div className="container text-center">
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          &copy; {new Date().getFullYear()} Digital Public Safety Platform (PS6) | ET AI Hackathon 2026
        </div>
      </div>
    </footer>
  );
};

export default Footer;
