import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Shield, Home, Activity, LayoutDashboard, FileBarChart2, Info } from 'lucide-react';

const Navbar = () => {
  const location = useLocation();
  const navLinks = [
    { name: 'Home',      path: '/',          icon: <Home size={15} /> },
    { name: 'Analyze',   path: '/analyze',   icon: <Activity size={15} /> },
    { name: 'Dashboard', path: '/dashboard', icon: <LayoutDashboard size={15} /> },
    { name: 'Reports',   path: '/reports',   icon: <FileBarChart2 size={15} /> },
    { name: 'About',     path: '/about',     icon: <Info size={15} /> },
  ];

  return (
    <div className="navbar-wrapper">
      <header className="navbar">
        {/* Brand Logo */}
        <Link to="/" className="nav-brand">
          <div className="nav-logo-icon">
            <Shield size={18} strokeWidth={2.4} />
          </div>
          <div>
            <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-heading)', lineHeight: 1.1 }}>
              DPSP
            </div>
            <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Intelligence Platform
            </div>
          </div>
        </Link>

        {/* Navigation Links */}
        <nav style={{ marginLeft: 'auto', marginRight: 'auto' }}>
          <ul className="nav-menu">
            {navLinks.map((link) => {
              const isActive = location.pathname === link.path;
              return (
                <li key={link.name}>
                  <Link 
                    to={link.path} 
                    className={`nav-item-link ${isActive ? 'active' : ''}`}
                  >
                    {link.icon}
                    <span>{link.name}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* Live Telemetry Badge */}
        <div className="nav-status-badge">
          <span className="status-dot" />
          <span>6 Engines Live</span>
        </div>
      </header>
    </div>
  );
};

export default Navbar;
