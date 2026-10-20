import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { getRecommendations } from '../api/agent'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return isActive ? 'nav-link nav-link--active' : 'nav-link'
}

function Layout() {
  const [pendingCount, setPendingCount] = useState(0)

  useEffect(() => {
    getRecommendations()
      .then(recs => setPendingCount(recs.filter(r => r.status === 'PENDING').length))
      .catch(() => {})
  }, [])

  return (
    <div className="app-shell">
      <nav className="topbar">
        <div className="brand">
          <span className="brand-mark">AaiTech</span>
        </div>
        <div className="nav-links">
          <NavLink to="/" end className={navLinkClass}>
            Dashboard
          </NavLink>
          <NavLink to="/analytics" className={navLinkClass}>
            Analytics Chat
          </NavLink>
          <NavLink to="/agent" className={navLinkClass}>
            Agent Recommendations
            {pendingCount > 0 && (
              <span style={{
                marginLeft: 6,
                background: 'var(--accent)',
                color: '#fff',
                fontSize: 10,
                fontWeight: 700,
                borderRadius: 10,
                padding: '1px 6px',
                verticalAlign: 'middle',
              }}>
                {pendingCount}
              </span>
            )}
          </NavLink>
        </div>
      </nav>
      <Outlet />
    </div>
  )
}

export default Layout
