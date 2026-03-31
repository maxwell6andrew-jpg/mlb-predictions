import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { searchAll } from '../api/client'

export default function SearchBar({ compact = false }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const wrapperRef = useRef(null)

  useEffect(() => {
    if (query.length < 2) {
      setResults(null)
      setOpen(false)
      return
    }
    const timer = setTimeout(async () => {
      try {
        const data = await searchAll(query)
        setResults(data)
        setOpen(true)
      } catch {
        setResults(null)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  useEffect(() => {
    function handleClick(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function go(path) {
    setQuery('')
    setOpen(false)
    navigate(path)
  }

  return (
    <div ref={wrapperRef} style={{ position: 'relative', width: '100%' }}>
      <input
        type="text"
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Search players or teams..."
        style={{
          width: '100%',
          padding: compact ? '8px 14px' : '12px 18px',
          fontSize: compact ? 14 : 16,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          color: 'var(--text-primary)',
          outline: 'none',
        }}
        onFocus={() => results && setOpen(true)}
      />
      {open && results && (
        <div style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          right: 0,
          marginTop: 4,
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          maxHeight: 360,
          overflowY: 'auto',
          zIndex: 200,
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>
          {results.teams?.length > 0 && (
            <div>
              <div style={{
                padding: '8px 14px',
                fontSize: 11,
                fontWeight: 600,
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
                letterSpacing: 0.5,
              }}>Teams</div>
              {results.teams.map(t => (
                <div key={t.id} onClick={() => go(`/team/${t.id}`)} style={{
                  padding: '10px 14px',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}>
                  <span style={{ fontWeight: 500 }}>{t.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{t.abbreviation}</span>
                </div>
              ))}
            </div>
          )}
          {results.players?.length > 0 && (
            <div>
              <div style={{
                padding: '8px 14px',
                fontSize: 11,
                fontWeight: 600,
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
                letterSpacing: 0.5,
                borderTop: results.teams?.length ? '1px solid var(--border)' : 'none',
              }}>Players</div>
              {results.players.map(p => (
                <div key={p.id} onClick={() => go(`/player/${p.id}`)} style={{
                  padding: '10px 14px',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}>
                  <span style={{ fontWeight: 500 }}>{p.name}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{p.position || ''}</span>
                </div>
              ))}
            </div>
          )}
          {(!results.teams?.length && !results.players?.length) && (
            <div style={{ padding: '16px 14px', color: 'var(--text-muted)', textAlign: 'center' }}>
              No results found
            </div>
          )}
        </div>
      )}
    </div>
  )
}
