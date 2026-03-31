import { useState, useEffect } from 'react'
import { getModelCoefficients, getModelValidation } from '../api/client'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'

function CoeffTable({ features }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-header">OLS Coefficients — Team Win Projection</div>
      <table>
        <thead>
          <tr>
            <th>Feature</th>
            <th className="right">Coef</th>
            <th className="right">Std Err</th>
            <th className="right">t-stat</th>
            <th className="right">p-value</th>
            <th className="right">Sig</th>
          </tr>
        </thead>
        <tbody>
          {features.map(f => (
            <tr key={f.name} style={{ opacity: f.significant ? 1 : 0.5 }}>
              <td style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 13 }}>{f.name}</td>
              <td className="right stat-number" style={{ color: f.coef > 0 ? 'var(--positive)' : 'var(--negative)' }}>
                {f.coef > 0 ? '+' : ''}{f.coef.toFixed(4)}
              </td>
              <td className="right stat-number">{f.std_err.toFixed(4)}</td>
              <td className="right stat-number">{f.t_stat.toFixed(2)}</td>
              <td className="right stat-number" style={{ color: f.p_value < 0.05 ? 'var(--positive)' : 'var(--negative)' }}>
                {f.p_value < 0.001 ? '<0.001' : f.p_value.toFixed(4)}
              </td>
              <td className="right">
                {f.significant
                  ? <span style={{ color: 'var(--positive)', fontSize: 16 }}>✓</span>
                  : <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>dropped</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RMSEChart({ walkForward }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-header">Walk-Forward Validation RMSE (wins)</div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={walkForward} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
          <XAxis dataKey="year" tick={{ fill: '#8892a4', fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: '#8892a4', fontSize: 12 }} axisLine={false} tickLine={false} domain={[0, 12]} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
            formatter={(v, n) => [v.toFixed(2), n]}
          />
          <ReferenceLine y={8} stroke="#374155" strokeDasharray="3 3" label={{ value: '8W avg', fill: '#5a6478', fontSize: 11 }} />
          <Bar dataKey="rmse" radius={[4, 4, 0, 0]} label={{ position: 'top', fill: '#8892a4', fontSize: 12, formatter: v => v.toFixed(1) }}>
            {walkForward.map((entry, i) => (
              <Cell key={i} fill={entry.rmse <= 7 ? '#22c55e' : entry.rmse <= 9 ? '#f97316' : '#ef4444'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function ModelPage() {
  const [coefs, setCoefs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getModelCoefficients()
      .then(setCoefs)
      .catch(err => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading model data</div>
  if (error) return <div className="error">Failed to load model: {error}</div>

  const { model, diagnostic_model, walk_forward, avg_rmse, roster_war_coefficient, interpretation, literature_notes } = coefs

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800 }}>
          Model <span style={{ color: 'var(--accent)' }}>Coefficients</span>
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4 }}>
          OLS regression fitted on Lahman historical data (2000–2025) · Walk-forward validated on last 4 seasons
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
        {[
          { label: 'R²', value: model.r_squared.toFixed(4), desc: 'Variance explained' },
          { label: 'In-sample RMSE', value: `${model.rmse_insample.toFixed(1)}W`, desc: 'Training error' },
          { label: 'Avg OOS RMSE', value: `${avg_rmse.toFixed(1)}W`, desc: 'Out-of-sample error' },
          { label: 'WAR coefficient', value: `${roster_war_coefficient.toFixed(3)}`, desc: 'Wins per WAR unit' },
        ].map(s => (
          <div key={s.label} className="card" style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 24, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)' }}>{s.value}</div>
            <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{s.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{s.desc}</div>
          </div>
        ))}
      </div>

      <div className="card-header" style={{ marginBottom: 8 }}>Prediction Model (Pythagorean — Literature-Preferred)</div>
      <CoeffTable features={model.features} />

      {diagnostic_model && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 8, padding: '0 4px' }}>
            Diagnostic: full 3-feature OLS (pyth_pct + actual_pct + run_diff collinear — included for transparency)
          </div>
          <CoeffTable features={diagnostic_model.features} />
        </div>
      )}

      {walk_forward?.length > 0 && <RMSEChart walkForward={walk_forward} />}

      {literature_notes && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">Academic Literature Grounding</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 14 }}>
            {[
              { label: 'Pythagorean Exponent', value: literature_notes.pythagorean_exponent, desc: 'Davenport & Woolner (1999)' },
              { label: 'YoY Persistence', value: literature_notes.year_over_year_persistence, desc: 'Tango et al., The Book (2006)' },
              { label: 'Runs per Win', value: literature_notes.runs_per_win, desc: 'OLS: ~10 runs = 1 win' },
            ].map(s => (
              <div key={s.label} style={{ background: 'var(--bg-hover)', borderRadius: 8, padding: '12px 14px' }}>
                <div style={{ fontSize: 20, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)' }}>{s.value}</div>
                <div style={{ fontSize: 13, fontWeight: 600, marginTop: 2 }}>{s.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{s.desc}</div>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            {literature_notes.why_pyth_over_actual}
          </p>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>Source: {literature_notes.source}</p>
        </div>
      )}

      <div className="card">
        <div className="card-header">Methodology</div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {interpretation}
        </p>
        <div style={{ marginTop: 12, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          <strong style={{ color: 'var(--text-primary)' }}>Feature selection rationale:</strong>
          <ul style={{ marginTop: 8, paddingLeft: 20 }}>
            <li><code style={{ fontFamily: 'JetBrains Mono, monospace' }}>pyth_pct_lag</code> — <strong>Preferred</strong>: Prior-year Pythagorean win% (RS^1.83 / (RS^1.83 + RA^1.83)). Less noise than actual W-L.</li>
            <li><code style={{ fontFamily: 'JetBrains Mono, monospace' }}>actual_pct_lag</code> — Collinear with pyth_pct (r≈0.85). Dropped per literature, shown in diagnostic model.</li>
            <li><code style={{ fontFamily: 'JetBrains Mono, monospace' }}>run_diff_pg_lag</code> — Redundant: Pythagorean is a smooth function of run differential. Dropped.</li>
          </ul>
          <div style={{ marginTop: 8 }}>
            Player projections use the <strong style={{ color: 'var(--text-primary)' }}>Marcel method</strong> (Tango):
            3-year weighted averages (5/4/3) regressed toward league mean, position-specific aging curves.
            Walk-forward RMSE of ~{avg_rmse.toFixed(1)}W compares to ZiPS/Steamer at ~6–8W with full transaction data.
          </div>
        </div>
      </div>
    </div>
  )
}
