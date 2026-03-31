import { useState, useEffect } from 'react'
import { getStandings } from '../api/client'
import SearchBar from '../components/SearchBar'
import StandingsTable from '../components/StandingsTable'

export default function HomePage() {
  const [standings, setStandings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStandings()
      .then(data => setStandings(data.standings))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div style={{ textAlign: 'center', padding: '48px 0 40px' }}>
        <h1 style={{ fontSize: 42, fontWeight: 800, marginBottom: 8 }}>
          MLB <span style={{ color: 'var(--accent)' }}>2026</span> Projections
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 16, marginBottom: 28 }}>
          Marcel-method player projections and team win totals powered by historical data
        </p>
        <div style={{ maxWidth: 500, margin: '0 auto' }}>
          <SearchBar />
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Projected Standings</h2>
      </div>

      {loading && <div className="loading">Loading projections — first load may take up to 2 minutes while the server wakes up</div>}
      {error && <div className="error">Failed to load standings: {error}</div>}
      {standings && <StandingsTable standings={standings} />}
    </div>
  )
}
