import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '8px 12px',
      fontSize: 13,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} style={{ color: p.color, fontFamily: 'JetBrains Mono, monospace' }}>
          {p.name}: {typeof p.value === 'number' ? p.value.toFixed(3) : p.value}
        </div>
      ))}
    </div>
  )
}

export default function ProjectionChart({ historical, projected, stats, title }) {
  const data = [
    ...historical.map(h => ({
      year: h.year,
      ...Object.fromEntries(stats.map(s => [s.label, h[s.key]])),
    })),
    {
      year: projected.year,
      ...Object.fromEntries(stats.map(s => [s.label, projected[s.key]])),
      isProjected: true,
    },
  ]

  const colors = ['#f97316', '#22c55e', '#3b82f6', '#a855f7']

  return (
    <div className="card">
      <div className="card-header">{title}</div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
          <XAxis
            dataKey="year"
            tick={{ fill: '#8892a4', fontSize: 12 }}
            axisLine={{ stroke: '#2a3448' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#8892a4', fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            domain={['auto', 'auto']}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            x={projected.year}
            stroke="#374155"
            strokeDasharray="3 3"
            label={{ value: 'Proj.', fill: '#5a6478', fontSize: 11, position: 'top' }}
          />
          {stats.map((s, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.label}
              stroke={colors[i % colors.length]}
              strokeWidth={2}
              dot={{ r: 4, fill: colors[i % colors.length] }}
              activeDot={{ r: 6 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
