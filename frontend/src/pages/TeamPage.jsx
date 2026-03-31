import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getTeam } from '../api/client'

function StatBox({ label, value, sub }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      borderRadius: 8,
      padding: '14px 16px',
      textAlign: 'center',
      minWidth: 100,
    }}>
      <div className="stat-number" style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export default function TeamPage() {
  const { teamId } = useParams()
  const [team, setTeam] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    getTeam(teamId)
      .then(data => setTeam(data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [teamId])

  if (loading) return <div className="loading">Loading team data</div>
  if (error) return <div className="error">{error}</div>
  if (!team) return null

  const winColor = team.projected_wins >= 89 ? 'var(--positive)' : team.projected_wins <= 73 ? 'var(--negative)' : 'var(--text-primary)'

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Link to="/" style={{ fontSize: 13, color: 'var(--text-muted)' }}>&larr; Back to standings</Link>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 4 }}>
        <h1 style={{ fontSize: 32, fontWeight: 800 }}>{team.name}</h1>
        <span style={{ fontSize: 16, color: 'var(--text-secondary)' }}>{team.league} {team.division}</span>
      </div>

      <div style={{ fontSize: 28, fontWeight: 800, color: winColor, marginBottom: 24 }} className="stat-number">
        {team.projected_wins}-{team.projected_losses}
      </div>

      {/* Projection breakdown */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">Projection Breakdown</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <StatBox label="Pythagorean" value={team.pythagorean_wins} sub="40% weight" />
          <StatBox label="Roster WAR" value={team.roster_war_wins} sub="35% weight" />
          <StatBox label="Regressed" value={team.regressed_wins} sub="25% weight" />
          <StatBox label="Proj. RS" value={team.projected_rs} />
          <StatBox label="Proj. RA" value={team.projected_ra} />
          <StatBox label="Team WAR" value={team.total_war?.toFixed(1)} />
        </div>
      </div>

      {/* Roster — Batters */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">Position Players</div>
        <table>
          <thead>
            <tr>
              <th>Player</th>
              <th>Pos</th>
              <th className="right">AVG</th>
              <th className="right">OPS</th>
              <th className="right">HR</th>
              <th className="right">WAR</th>
            </tr>
          </thead>
          <tbody>
            {(team.batters || []).sort((a, b) => b.war - a.war).map(p => (
              <tr key={p.id}>
                <td>
                  <Link to={`/player/${p.id}`} style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                    {p.name}
                  </Link>
                </td>
                <td style={{ color: 'var(--text-muted)' }}>{p.position}</td>
                <td className="right stat-number">{p.avg?.toFixed(3).slice(1) ?? '---'}</td>
                <td className="right stat-number">{p.ops?.toFixed(3).slice(1) ?? '---'}</td>
                <td className="right stat-number">{p.hr ?? '-'}</td>
                <td className="right stat-number" style={{
                  color: p.war >= 3 ? 'var(--positive)' : p.war >= 1 ? 'var(--accent)' : 'var(--text-primary)',
                }}>{p.war?.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Roster — Pitchers */}
      <div className="card">
        <div className="card-header">Pitchers</div>
        <table>
          <thead>
            <tr>
              <th>Player</th>
              <th className="right">ERA</th>
              <th className="right">WHIP</th>
              <th className="right">K/9</th>
              <th className="right">IP</th>
              <th className="right">WAR</th>
            </tr>
          </thead>
          <tbody>
            {(team.pitchers || []).sort((a, b) => b.war - a.war).map(p => (
              <tr key={p.id}>
                <td>
                  <Link to={`/player/${p.id}`} style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                    {p.name}
                  </Link>
                </td>
                <td className="right stat-number">{p.era?.toFixed(2) ?? '---'}</td>
                <td className="right stat-number">{p.whip?.toFixed(2) ?? '---'}</td>
                <td className="right stat-number">{p.k_per_9?.toFixed(1) ?? '---'}</td>
                <td className="right stat-number">{p.ip?.toFixed(0) ?? '-'}</td>
                <td className="right stat-number" style={{
                  color: p.war >= 3 ? 'var(--positive)' : p.war >= 1 ? 'var(--accent)' : 'var(--text-primary)',
                }}>{p.war?.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
