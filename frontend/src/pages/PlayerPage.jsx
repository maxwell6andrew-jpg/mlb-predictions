import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getPlayer } from '../api/client'
import ProjectionChart from '../components/ProjectionChart'
import LeagueComparison from '../components/LeagueComparison'

function ConfidenceBadge({ confidence }) {
  const level = confidence >= 0.7 ? 'high' : confidence >= 0.4 ? 'medium' : 'low'
  const label = level.charAt(0).toUpperCase() + level.slice(1) + ' Confidence'
  return <span className={`badge badge-${level}`}>{label}</span>
}

function StatCard({ label, value, format = 'number' }) {
  let display = value
  if (format === 'avg') display = value?.toFixed(3).slice(1) ?? '---'
  else if (format === 'rate') display = value?.toFixed(2) ?? '---'
  else if (format === 'dec1') display = value?.toFixed(1) ?? '---'
  else if (format === 'int') display = Math.round(value) ?? '-'
  else display = value ?? '-'

  return (
    <div style={{
      background: 'var(--bg-surface)',
      borderRadius: 8,
      padding: '12px 16px',
      textAlign: 'center',
      minWidth: 80,
    }}>
      <div className="stat-number" style={{ fontSize: 22, fontWeight: 700 }}>{display}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{label}</div>
    </div>
  )
}

export default function PlayerPage() {
  const { playerId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getPlayer(playerId)
      .then(d => setData(d))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [playerId])

  if (loading) return <div className="loading">Loading player projection</div>
  if (error) return <div className="error">{error}</div>
  if (!data) return null

  const { player, projection, historical, league_averages } = data
  const isBatter = projection.type === 'batting'

  const battingCompareStats = [
    { key: 'avg', label: 'AVG' },
    { key: 'obp', label: 'OBP' },
    { key: 'slg', label: 'SLG' },
    { key: 'hr_rate', label: 'HR/PA' },
  ]

  const pitchingCompareStats = [
    { key: 'era', label: 'ERA', invert: true },
    { key: 'whip', label: 'WHIP', invert: true },
    { key: 'k_per_9', label: 'K/9' },
    { key: 'bb_per_9', label: 'BB/9', invert: true },
  ]

  const battingChartStats = [
    { key: 'avg', label: 'AVG' },
    { key: 'ops', label: 'OPS' },
  ]

  const pitchingChartStats = [
    { key: 'era', label: 'ERA' },
    { key: 'whip', label: 'WHIP' },
  ]

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Link to="/" style={{ fontSize: 13, color: 'var(--text-muted)' }}>&larr; Back to standings</Link>
      </div>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <h1 style={{ fontSize: 32, fontWeight: 800 }}>{player.name}</h1>
          <ConfidenceBadge confidence={projection.confidence} />
        </div>
        <div style={{ color: 'var(--text-secondary)', fontSize: 15 }}>
          {player.team} &middot; {player.position} &middot; Age {player.age}
          {player.bats && <> &middot; Bats: {player.bats}</>}
          {player.throws && <> &middot; Throws: {player.throws}</>}
        </div>
      </div>

      {/* Projected Stats */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">2026 Projected Stats</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {isBatter ? (
            <>
              <StatCard label="AVG" value={projection.avg} format="avg" />
              <StatCard label="OBP" value={projection.obp} format="avg" />
              <StatCard label="SLG" value={projection.slg} format="avg" />
              <StatCard label="OPS" value={projection.ops} format="avg" />
              <StatCard label="HR" value={projection.hr} format="int" />
              <StatCard label="RBI" value={projection.rbi} format="int" />
              <StatCard label="SB" value={projection.sb} format="int" />
              <StatCard label="PA" value={projection.projected_pa} format="int" />
              <StatCard label="WAR" value={projection.war} format="dec1" />
            </>
          ) : (
            <>
              <StatCard label="ERA" value={projection.era} format="rate" />
              <StatCard label="WHIP" value={projection.whip} format="rate" />
              <StatCard label="K/9" value={projection.k_per_9} format="dec1" />
              <StatCard label="BB/9" value={projection.bb_per_9} format="dec1" />
              <StatCard label="W" value={projection.w} format="int" />
              <StatCard label="IP" value={projection.projected_ip} format="int" />
              <StatCard label="WAR" value={projection.war} format="dec1" />
            </>
          )}
        </div>
      </div>

      {/* Charts row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16, marginBottom: 16 }}>
        <LeagueComparison
          projection={projection}
          leagueAvg={league_averages}
          stats={isBatter ? battingCompareStats : pitchingCompareStats}
        />
        {historical?.length > 0 && (
          <ProjectionChart
            historical={historical}
            projected={{ year: 2026, ...projection }}
            stats={isBatter ? battingChartStats : pitchingChartStats}
            title="Historical Trend"
          />
        )}
      </div>
    </div>
  )
}
