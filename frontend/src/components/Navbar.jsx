import { Link, useLocation } from 'react-router-dom'
import SearchBar from './SearchBar'

const NAV_LINKS = [
  { to: '/', label: 'Standings' },
  { to: '/matchups', label: "Today's Games" },
  { to: '/season', label: 'Season' },
  { to: '/model', label: 'Model' },
]

export default function Navbar() {
  const location = useLocation()
  return (
    <nav style={{
      background: 'var(--bg-surface)',
      borderBottom: '1px solid var(--border)',
      padding: '0 20px',
      height: 60,
      display: 'flex',
      alignItems: 'center',
      gap: 24,
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      <Link to="/" style={{
        fontSize: 20,
        fontWeight: 800,
        color: 'var(--text-primary)',
        textDecoration: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexShrink: 0,
      }}>
        <span style={{ fontSize: 22 }}>&#9918;</span>
        <span>MLB <span style={{ color: 'var(--accent)' }}>Predictor</span></span>
      </Link>
      <div style={{ display: 'flex', gap: 4 }}>
        {NAV_LINKS.map(link => {
          const active = location.pathname === link.to
          return (
            <Link key={link.to} to={link.to} style={{
              padding: '6px 14px',
              borderRadius: 6,
              fontSize: 14,
              fontWeight: active ? 600 : 400,
              color: active ? 'var(--accent)' : 'var(--text-secondary)',
              background: active ? 'rgba(249,115,22,0.1)' : 'transparent',
              textDecoration: 'none',
              whiteSpace: 'nowrap',
            }}>
              {link.label}
            </Link>
          )
        })}
      </div>
      <div style={{ flex: 1, maxWidth: 320 }}>
        <SearchBar compact />
      </div>
    </nav>
  )
}
