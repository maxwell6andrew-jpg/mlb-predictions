import { Link } from 'react-router-dom'

const DIVISION_ORDER = [
  'American League East', 'American League Central', 'American League West',
  'National League East', 'National League Central', 'National League West',
]

const SHORT_NAME = {
  'American League East': 'AL East',
  'American League Central': 'AL Central',
  'American League West': 'AL West',
  'National League East': 'NL East',
  'National League Central': 'NL Central',
  'National League West': 'NL West',
}

export default function StandingsTable({ standings }) {
  const grouped = {}
  for (const team of standings) {
    const div = team.division
    if (!grouped[div]) grouped[div] = []
    grouped[div].push(team)
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
      {DIVISION_ORDER.map(div => {
        const teams = grouped[div]
        if (!teams) return null
        const isAL = div.startsWith('American')
        const displayName = SHORT_NAME[div] || div
        return (
          <div key={div} className="card">
            <div style={{
              fontSize: 14,
              fontWeight: 700,
              marginBottom: 12,
              color: isAL ? 'var(--al-blue)' : 'var(--nl-red)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              <span style={{
                width: 4,
                height: 16,
                borderRadius: 2,
                background: isAL ? 'var(--al-blue)' : 'var(--nl-red)',
              }} />
              {displayName}
            </div>
            <table>
              <thead>
                <tr>
                  <th style={{ width: 30 }}>#</th>
                  <th>Team</th>
                  <th className="right">W</th>
                  <th className="right">L</th>
                  <th className="right">Win%</th>
                </tr>
              </thead>
              <tbody>
                {teams.sort((a, b) => b.projected_wins - a.projected_wins).map((t, i) => (
                  <tr key={t.team_id}>
                    <td style={{ color: 'var(--text-muted)' }}>{i + 1}</td>
                    <td>
                      <Link to={`/team/${t.team_id}`} style={{
                        fontWeight: 500,
                        color: 'var(--text-primary)',
                      }}>
                        {t.name}
                      </Link>
                    </td>
                    <td className="right stat-number">{t.projected_wins}</td>
                    <td className="right stat-number">{t.projected_losses}</td>
                    <td className="right stat-number" style={{
                      color: t.win_pct >= .550 ? 'var(--positive)' : t.win_pct < .450 ? 'var(--negative)' : 'var(--text-primary)',
                    }}>
                      {t.win_pct.toFixed(3).slice(1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}
