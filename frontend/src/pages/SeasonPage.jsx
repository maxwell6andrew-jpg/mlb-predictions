import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getSeasonProjections } from '../api/client'

const TREND_COLOR = { ahead: 'var(--positive)', behind: 'var(--negative)', on_track: 'var(--accent)', too_early: 'var(--text-muted)', season_not_started: 'var(--text-muted)' }
const TREND_LABEL = { ahead: '▲ Ahead', behind: '▼ Behind', on_track: '→ On track', too_early: 'Too early', season_not_started: 'Pre-season' }

function CIBar({ projected, ciLow, ciHigh }) {
  const min = 40, max = 120
  const range = max - min
  const lowPct = ((ciLow - min) / range) * 100
  const highPct = ((ciHigh - min) / range) * 100
  const projPct = ((projected - min) / range) * 100
  return (
    <div style={{ position: 'relative', height: 12, marginTop: 4 }}>
      <div style={{ position: 'absolute', top: 3, left: 0, right: 0, height: 6, background: 'var(--border)', borderRadius: 3 }} />
      <div style={{
        position: 'absolute', top: 3, left: `${lowPct}%`, width: `${highPct - lowPct}%`,
        height: 6, background: 'rgba(249,115,22,0.35)', borderRadius: 3,
      }} />
      <div style={{
        position: 'absolute', top: 1, left: `${projPct}%`, transform: 'translateX(-50%)',
        width: 10, height: 10, background: 'var(--accent)', borderRadius: '50%',
      }} />
    </div>
  )
}

function TeamRow({ team, rank }) {
  const pace = team.pace || {}
  return (
    <tr>
      <td style={{ color: 'var(--text-muted)', width: 32 }}>{rank}</td>
      <td>
        <Link to={`/team/${team.team_id}`} style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
          {team.name}
        </Link>
      </td>
      <td className="right stat-number" style={{ fontSize: 16, fontWeight: 700, color: team.projected_wins >= 92 ? 'var(--positive)' : team.projected_wins < 72 ? 'var(--negative)' : 'var(--text-primary)' }}>
        {team.projected_wins}
      </td>
      <td className="right stat-number" style={{ color: 'var(--text-secondary)' }}>{team.projected_losses}</td>
      <td className="right" style={{ minWidth: 140 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          [{team.ci_low}–{team.ci_high}]
        </div>
        <CIBar projected={team.projected_wins} ciLow={team.ci_low} ciHigh={team.ci_high} />
      </td>
      <td className="right stat-number">{team.total_war?.toFixed(1)}</td>
      <td className="right">
        {pace.status === 'active' ? (
          <div>
            <div className="stat-number" style={{ fontSize: 13 }}>{pace.current_wins}-{pace.current_losses}</div>
            <div style={{ fontSize: 11, color: TREND_COLOR[pace.trend] }}>
              {TREND_LABEL[pace.trend]} ({pace.pace_wins}W pace)
            </div>
          </div>
        ) : (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{TREND_LABEL[pace.status] || '—'}</span>
        )}
      </td>
      <td style={{ maxWidth: 280, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
        {team.narrative}
      </td>
    </tr>
  )
}

const DIVISION_ORDER = [
  'American League East', 'American League Central', 'American League West',
  'National League East', 'National League Central', 'National League West',
]

export default function SeasonPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState('division') // 'division' | 'league' | 'all'

  useEffect(() => {
    getSeasonProjections()
      .then(setData)
      .catch(err => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading season projections</div>
  if (error) return <div className="error">Failed to load: {error}</div>

  const teams = data?.teams || []

  const grouped = {}
  for (const t of teams) {
    const div = t.division || 'Unknown'
    if (!grouped[div]) grouped[div] = []
    grouped[div].push(t)
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 800 }}>
            {data?.season} <span style={{ color: 'var(--accent)' }}>Season Projections</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4 }}>
            90% confidence intervals via walk-forward RMSE ({data?.model_rmse}W σ) · OLS-fitted weights
          </p>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>
          Updated<br />{data?.last_updated}
        </div>
      </div>

      {DIVISION_ORDER.map(div => {
        const divTeams = grouped[div]
        if (!divTeams) return null
        const isAL = div.startsWith('American')
        return (
          <div key={div} className="card" style={{ marginBottom: 16 }}>
            <div style={{
              fontSize: 14, fontWeight: 700, marginBottom: 14,
              color: isAL ? 'var(--al-blue)' : 'var(--nl-red)',
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <span style={{ width: 4, height: 16, borderRadius: 2, background: isAL ? 'var(--al-blue)' : 'var(--nl-red)', display: 'inline-block' }} />
              {div}
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 32 }}>#</th>
                    <th>Team</th>
                    <th className="right">W</th>
                    <th className="right">L</th>
                    <th className="right">90% CI</th>
                    <th className="right">WAR</th>
                    <th className="right">Pace</th>
                    <th>Key Driver</th>
                  </tr>
                </thead>
                <tbody>
                  {divTeams.map((t, i) => (
                    <TeamRow key={t.team_id} team={t} rank={i + 1} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}

      <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', marginTop: 8 }}>
        CI = 90% confidence interval from walk-forward validated RMSE · WAR = projected roster wins above replacement
      </div>
    </div>
  )
}
