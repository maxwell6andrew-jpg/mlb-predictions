import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine
} from 'recharts'

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 13,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.stat}</div>
      <div style={{ fontFamily: 'JetBrains Mono, monospace' }}>
        Player: {d.player.toFixed(3)} | Lg Avg: {d.league.toFixed(3)}
      </div>
    </div>
  )
}

export default function LeagueComparison({ projection, leagueAvg, stats }) {
  const data = stats.map(s => {
    const playerVal = projection[s.key] || 0
    const lgVal = leagueAvg[s.key] || 0
    const diff = s.invert ? lgVal - playerVal : playerVal - lgVal
    return {
      stat: s.label,
      diff,
      player: playerVal,
      league: lgVal,
      positive: diff >= 0,
    }
  })

  return (
    <div className="card">
      <div className="card-header">vs League Average</div>
      <ResponsiveContainer width="100%" height={stats.length * 40 + 20}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 50 }}>
          <XAxis type="number" tick={{ fill: '#8892a4', fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="stat"
            tick={{ fill: '#e2e8f0', fontSize: 13, fontWeight: 500 }}
            axisLine={false}
            tickLine={false}
            width={50}
          />
          <Tooltip content={<CustomTooltip />} cursor={false} />
          <ReferenceLine x={0} stroke="#374155" />
          <Bar dataKey="diff" radius={[0, 4, 4, 0]} barSize={20}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.positive ? '#22c55e' : '#ef4444'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
