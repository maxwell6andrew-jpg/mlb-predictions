import { useState, useEffect } from 'react'
import { getModelCoefficients } from '../api/client'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'

function Card({ children, style }) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 10,
      padding: '20px 22px',
      marginBottom: 16,
      ...style,
    }}>
      {children}
    </div>
  )
}

function CardTitle({ children, sub }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{children}</h3>
      {sub && <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>{sub}</p>}
    </div>
  )
}

function StatBox({ label, value, desc, color }) {
  return (
    <div style={{
      background: 'var(--bg-hover)',
      borderRadius: 8,
      padding: '14px 16px',
      textAlign: 'center',
    }}>
      <div style={{
        fontSize: 22, fontWeight: 800,
        fontFamily: 'JetBrains Mono, monospace',
        color: color || 'var(--accent)',
      }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{label}</div>
      {desc && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{desc}</div>}
    </div>
  )
}

function LayerBadge({ number, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%',
        background: 'var(--accent)', color: '#fff',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, fontWeight: 800, flexShrink: 0,
      }}>{number}</div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>{label}</h2>
    </div>
  )
}

function CoeffTable({ features }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            <th style={{ textAlign: 'left', padding: '8px 6px', color: 'var(--text-muted)', fontWeight: 600 }}>Feature</th>
            <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)', fontWeight: 600 }}>Coef</th>
            <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)', fontWeight: 600 }}>Std Err</th>
            <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)', fontWeight: 600 }}>p-value</th>
            <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)', fontWeight: 600 }}>Sig</th>
          </tr>
        </thead>
        <tbody>
          {features.map(f => (
            <tr key={f.name} style={{ borderBottom: '1px solid var(--border)', opacity: f.significant ? 1 : 0.5 }}>
              <td style={{ padding: '8px 6px', fontFamily: 'JetBrains Mono, monospace' }}>{f.name}</td>
              <td style={{ textAlign: 'right', padding: '8px 6px', fontFamily: 'monospace', color: f.coef > 0 ? 'var(--positive)' : 'var(--negative)' }}>
                {f.coef > 0 ? '+' : ''}{f.coef.toFixed(4)}
              </td>
              <td style={{ textAlign: 'right', padding: '8px 6px', fontFamily: 'monospace' }}>{f.std_err.toFixed(4)}</td>
              <td style={{ textAlign: 'right', padding: '8px 6px', fontFamily: 'monospace', color: f.p_value < 0.05 ? 'var(--positive)' : 'var(--negative)' }}>
                {f.p_value < 0.001 ? '<0.001' : f.p_value.toFixed(4)}
              </td>
              <td style={{ textAlign: 'right', padding: '8px 6px' }}>
                {f.significant
                  ? <span style={{ color: 'var(--positive)' }}>&#10003;</span>
                  : <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>dropped</span>}
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
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={walkForward} margin={{ top: 8, right: 12, bottom: 0, left: -10 }}>
        <XAxis dataKey="year" tick={{ fill: '#8892a4', fontSize: 12 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: '#8892a4', fontSize: 12 }} axisLine={false} tickLine={false} domain={[0, 14]} />
        <Tooltip
          contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
          formatter={(v) => [v.toFixed(2) + ' wins', 'RMSE']}
        />
        <ReferenceLine y={10} stroke="#374155" strokeDasharray="3 3" label={{ value: 'Marcel baseline', fill: '#5a6478', fontSize: 11 }} />
        <Bar dataKey="rmse" radius={[4, 4, 0, 0]} label={{ position: 'top', fill: '#8892a4', fontSize: 11, formatter: v => v.toFixed(1) }}>
          {walkForward.map((entry, i) => (
            <Cell key={i} fill={entry.rmse <= 8 ? '#22c55e' : entry.rmse <= 10 ? '#f97316' : '#ef4444'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function ModelPage() {
  const [coefs, setCoefs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeLayer, setActiveLayer] = useState(null)

  useEffect(() => {
    getModelCoefficients()
      .then(setCoefs)
      .catch(err => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800 }}>
          How the <span style={{ color: 'var(--accent)' }}>Model</span> Works
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4, maxWidth: 640, lineHeight: 1.6 }}>
          Five layers chained together: player projections feed into team win totals, which feed into daily game probabilities. Everything is transparent.
        </p>
      </div>

      {/* Pipeline overview */}
      <Card>
        <CardTitle sub="Each layer's output feeds into the next">Model Pipeline</CardTitle>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            { n: 1, label: 'Marcel Projections', color: '#3b82f6' },
            { n: 2, label: 'Statcast Corrections', color: '#8b5cf6' },
            { n: 3, label: 'Team Win Totals', color: '#f97316' },
            { n: 4, label: 'Bayesian Updating', color: '#22c55e' },
            { n: 5, label: 'Game Predictions', color: '#ef4444' },
          ].map((step, i) => (
            <div key={step.n} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{
                background: step.color, color: '#fff', borderRadius: '50%',
                width: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, fontWeight: 700,
              }}>{step.n}</div>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{step.label}</span>
              {i < 4 && <span style={{ color: 'var(--text-muted)', margin: '0 4px' }}>&#8594;</span>}
            </div>
          ))}
        </div>
      </Card>

      {/* ============================================================ */}
      {/* LAYER 1: Marcel */}
      {/* ============================================================ */}
      <LayerBadge number={1} label="Player Projections (Marcel Method)" />

      <Card>
        <CardTitle sub="Tom Tango's baseline projection system — 3 years of history, regressed to the mean">
          Marcel: Four Steps
        </CardTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12, marginBottom: 16 }}>
          {[
            { step: 'Weighted Average', desc: 'Last 3 years weighted 5/4/3. Most recent season counts most. Rate stats computed per plate appearance.' },
            { step: 'Regression to Mean', desc: 'Each stat is pulled toward the league average. Noisy stats (AVG: 1000 PA) regress harder than stable ones (K rate: 400 PA).' },
            { step: 'Aging Curves', desc: 'Stat-specific peaks: power at 28-29, speed at 25-26, plate discipline at 28. Position-adjusted (catchers decline faster).' },
            { step: 'Playing Time', desc: 'Weighted PA average regressed 20% toward 400 PA baseline. Players over 33 get an additional discount.' },
          ].map(s => (
            <div key={s.step} style={{ background: 'var(--bg-hover)', borderRadius: 8, padding: 14 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#3b82f6', marginBottom: 6 }}>{s.step}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{s.desc}</div>
            </div>
          ))}
        </div>

        <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>
          <strong style={{ color: 'var(--text-secondary)' }}>Regression constants:</strong>{' '}
          AVG=1000 PA, OBP=900, SLG=1000, HR rate=800, BB rate=800, K rate=400, SB rate=1200.
          Higher constants mean more regression (noisier stats). AVG and HR use lower constants to preserve more of elite hitters' true talent signal.
        </div>
      </Card>

      <Card>
        <CardTitle sub="Backtest: 2,661 batter-seasons and 2,515 pitcher-seasons across 2017-2025">
          Player Projection Accuracy
        </CardTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 10 }}>
          <StatBox label="AVG corr." value="0.460" desc="Batting average" color="#3b82f6" />
          <StatBox label="OPS corr." value="0.490" desc="On-base + slugging" color="#3b82f6" />
          <StatBox label="HR corr." value="0.538" desc="Home runs" color="#3b82f6" />
          <StatBox label="K/9 corr." value="0.659" desc="Pitcher strikeouts" color="#8b5cf6" />
          <StatBox label="ERA corr." value="0.195" desc="Earned run avg" color="#8b5cf6" />
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 10 }}>
          ERA correlation is low because ERA depends heavily on defense and luck. This is why Layer 2 (Statcast) matters — xERA is far more stable.
        </p>
      </Card>

      {/* ============================================================ */}
      {/* LAYER 2: Statcast */}
      {/* ============================================================ */}
      <LayerBadge number={2} label="Statcast Corrections" />

      <Card>
        <CardTitle sub="Adjusts Marcel projections using batted ball quality data from Baseball Savant. Stat-specific blend weights give more influence to Statcast where it's most predictive.">
          Stat-Specific Statcast Blending
        </CardTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12, marginBottom: 16 }}>
          <div style={{ background: 'var(--bg-hover)', borderRadius: 8, padding: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#8b5cf6', marginBottom: 8 }}>Batting Adjustments</div>
            <ul style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, paddingLeft: 18 }}>
              <li><strong>xBA direct blend (45%):</strong> Marcel AVG is blended directly toward Statcast xBA — the most predictive AVG signal available</li>
              <li><strong>xwOBA luck correction:</strong> If actual wOBA is below xwOBA, the player was unlucky — nudge OBP and SLG up</li>
              <li><strong>Barrel rate &#8594; HR (40%):</strong> The single best HR predictor. High barrel rate with low HR total signals regression upward</li>
              <li><strong>Exit velocity &#8594; SLG (40%):</strong> Hard contact with low SLG suggests bad BABIP luck</li>
              <li><strong>Park factors:</strong> Half home games at team park, half neutral. Coors +35%, Oracle -12%</li>
            </ul>
          </div>
          <div style={{ background: 'var(--bg-hover)', borderRadius: 8, padding: 14 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#8b5cf6', marginBottom: 8 }}>Pitching Adjustments</div>
            <ul style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, paddingLeft: 18 }}>
              <li><strong>xERA correction:</strong> Blend Marcel ERA toward Statcast expected ERA</li>
              <li><strong>Barrel rate against &#8594; HR/9:</strong> High barrel rate against means more HR allowed</li>
              <li><strong>xwOBA against luck:</strong> If opponents had low xwOBA but high actual wOBA, pitcher was unlucky</li>
              <li><strong>Park factor for ERA:</strong> Pitchers in hitter-friendly parks get ERA adjusted down</li>
            </ul>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 }}>
          <StatBox label="AVG (xBA)" value="45%" desc="Highest blend — xBA is very predictive" color="#8b5cf6" />
          <StatBox label="HR (Barrel)" value="40%" desc="Barrel rate is best HR predictor" color="#8b5cf6" />
          <StatBox label="SLG / EV" value="40%" desc="Exit velo + xSLG signal" color="#8b5cf6" />
          <StatBox label="ERA / Other" value="35%" desc="Default Statcast weight" color="var(--text-secondary)" />
          <StatBox label="Lg Barrel %" value="7.5%" desc="League avg barrel rate" color="var(--text-secondary)" />
          <StatBox label="Lg xwOBA" value=".310" desc="League avg xwOBA" color="var(--text-secondary)" />
        </div>
      </Card>

      {/* ============================================================ */}
      {/* LAYER 3: Team Wins */}
      {/* ============================================================ */}
      <LayerBadge number={3} label="Team Win Projections" />

      <Card>
        <CardTitle sub="OLS regression on prior-year Pythagorean win%, plus roster WAR and Vegas consensus">
          Three-Component Model
        </CardTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 16 }}>
          {[
            { label: 'Pythagorean Wins', pct: '40%', desc: 'RS^1.83 / (RS^1.83 + RA^1.83). Filters out close-game luck.', color: '#f97316' },
            { label: 'Roster WAR', pct: '35%', desc: 'Sum of Marcel player projections. WAR differential from league-average (18 WAR).', color: '#f97316' },
            { label: 'Regressed Wins', pct: '25%', desc: 'Last year\'s record pulled 40% toward 81 wins. 100-win team projects ~92.', color: '#f97316' },
          ].map(c => (
            <div key={c.label} style={{ background: 'var(--bg-hover)', borderRadius: 8, padding: 14, textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: c.color, fontFamily: 'JetBrains Mono, monospace' }}>{c.pct}</div>
              <div style={{ fontSize: 13, fontWeight: 700, marginTop: 4 }}>{c.label}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.5 }}>{c.desc}</div>
            </div>
          ))}
        </div>

        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 12 }}>
          The OLS model also blends 40% with Vegas preseason consensus win totals. Vegas lines aggregate
          injury news, minor league depth, front office moves, and market wisdom that no box-score model can see.
          The blend reduces RMSE from ~10.9 (pure model) to ~10.0 wins.
        </div>
      </Card>

      {/* Live OLS data from API */}
      {loading && <Card><p style={{ color: 'var(--text-muted)' }}>Loading live model data...</p></Card>}
      {error && <Card><p style={{ color: 'var(--negative)' }}>Could not load live model data: {error}</p></Card>}

      {coefs && (
        <>
          <Card>
            <CardTitle sub="OLS regression trained on Lahman data 2000-2025 (excluding 2020)">
              OLS Coefficient Table
            </CardTitle>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 16 }}>
              <StatBox label="R-squared" value={coefs.model.r_squared.toFixed(3)} desc="Variance explained" />
              <StatBox label="OOS RMSE" value={`${coefs.avg_rmse.toFixed(1)}W`} desc="Walk-forward error" />
              <StatBox label="WAR Coef" value={coefs.roster_war_coefficient.toFixed(2)} desc="Wins per WAR above avg" />
            </div>
            <CoeffTable features={coefs.model.features} />
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 10 }}>
              Only pyth_pct_lag is used (literature-preferred). Actual W% and run diff are collinear (r~0.85) and dropped per Tango et al.
            </p>
          </Card>

          {coefs.walk_forward?.length > 0 && (
            <Card>
              <CardTitle sub="Train on all years before N, predict year N, measure error">
                Walk-Forward Validation
              </CardTitle>
              <RMSEChart walkForward={coefs.walk_forward} />
            </Card>
          )}
        </>
      )}

      <Card>
        <CardTitle>Team RMSE Comparison</CardTitle>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ textAlign: 'left', padding: '8px 6px', color: 'var(--text-muted)' }}>Method</th>
                <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)' }}>RMSE</th>
                <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)' }}>Source</th>
              </tr>
            </thead>
            <tbody>
              {[
                { method: 'Vegas lines', rmse: '~7-8', src: 'Market consensus', highlight: false },
                { method: 'ZiPS / Steamer / PECOTA', rmse: '~9-10', src: 'Professional systems', highlight: false },
                { method: 'Our model (+ Vegas blend)', rmse: '~10.0', src: 'Backtested 2017-2025', highlight: true },
                { method: 'Pure Marcel (no extras)', rmse: '~10.9', src: 'Base projection only', highlight: false },
                { method: 'Last year\'s record', rmse: '~12.6', src: 'Naive baseline', highlight: false },
                { method: 'Always guess 81', rmse: '~13.5', src: 'Null model', highlight: false },
              ].map(r => (
                <tr key={r.method} style={{ borderBottom: '1px solid var(--border)', background: r.highlight ? 'rgba(249,115,22,0.08)' : 'transparent' }}>
                  <td style={{ padding: '10px 6px', fontWeight: r.highlight ? 700 : 400, color: r.highlight ? 'var(--accent)' : 'var(--text-primary)' }}>{r.method}</td>
                  <td style={{ textAlign: 'right', padding: '10px 6px', fontFamily: 'monospace', fontWeight: r.highlight ? 700 : 400 }}>{r.rmse}</td>
                  <td style={{ textAlign: 'right', padding: '10px 6px', color: 'var(--text-muted)', fontSize: 12 }}>{r.src}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ============================================================ */}
      {/* LAYER 4: Bayesian */}
      {/* ============================================================ */}
      <LayerBadge number={4} label="In-Season Bayesian Updating" />

      <Card>
        <CardTitle sub="The preseason number is the prior. Game results are new evidence. The blend shifts as the season goes on.">
          In-season weight = games played / (games played + 69)
        </CardTitle>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          Why 69? It comes from the ratio of single-game variance (0.25) to true-talent variance (~0.0036).
          It takes about 69 games before in-season results carry as much information as the entire preseason projection.
          In April, the preseason number dominates. By mid-July, the model is mostly tracking what happened on the field.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 14 }}>
          {[
            { games: '30', date: 'Late Apr', preW: '70%', inW: '30%', rmse: '4.0' },
            { games: '69', date: 'Mid Jun', preW: '50%', inW: '50%', rmse: '2.3' },
            { games: '100', date: 'Late Jul', preW: '41%', inW: '59%', rmse: '1.6' },
            { games: '130', date: 'Sep', preW: '35%', inW: '65%', rmse: '0.9' },
          ].map(r => (
            <div key={r.games} style={{ background: 'var(--bg-hover)', borderRadius: 8, padding: 12, textAlign: 'center' }}>
              <div style={{ fontSize: 20, fontWeight: 800, color: '#22c55e', fontFamily: 'monospace' }}>{r.rmse}W</div>
              <div style={{ fontSize: 12, fontWeight: 600, marginTop: 4 }}>{r.games} games ({r.date})</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>Pre {r.preW} / In {r.inW}</div>
            </div>
          ))}
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          RMSE drops from ~10 wins (preseason) to under 1 win by September. Confidence intervals shrink accordingly.
        </p>
      </Card>

      {/* ============================================================ */}
      {/* LAYER 5: Game Predictions */}
      {/* ============================================================ */}
      <LayerBadge number={5} label="Game-Level Predictions" />

      <Card>
        <CardTitle sub="Log5 base probability plus six game-specific adjustments">
          Daily Matchup Engine
        </CardTitle>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          Bill James' log5 formula converts two teams' winning percentages into a head-to-head probability.
          A .600 team vs a .450 team gets about 64.6%. From there, six adjustments are layered on:
        </p>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={{ textAlign: 'left', padding: '8px 6px', color: 'var(--text-muted)' }}>Factor</th>
                <th style={{ textAlign: 'left', padding: '8px 6px', color: 'var(--text-muted)' }}>What It Does</th>
                <th style={{ textAlign: 'right', padding: '8px 6px', color: 'var(--text-muted)' }}>Impact</th>
              </tr>
            </thead>
            <tbody>
              {[
                { factor: 'Home field', desc: 'Home teams win ~54% historically', impact: '+3.5%' },
                { factor: 'Starting pitching', desc: 'FIP gap between starters, converted to expected run savings over ~5.5 IP', impact: 'High' },
                { factor: 'Offense (OPS)', desc: 'Lineup OPS differential between projected lineups', impact: 'Medium' },
                { factor: 'Bullpen ERA', desc: 'Bullpen ERA gap over ~3.5 relief innings', impact: 'Medium' },
                { factor: 'Park effects', desc: 'Venue-specific run and HR multipliers for all 30 parks', impact: 'Low-Med' },
                { factor: 'Platoon splits', desc: 'LHB vs LHP = ~8% OPS penalty. Weighted by lineup handedness.', impact: 'Low-Med' },
              ].map(r => (
                <tr key={r.factor} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td style={{ padding: '10px 6px', fontWeight: 600, color: '#ef4444' }}>{r.factor}</td>
                  <td style={{ padding: '10px 6px', color: 'var(--text-secondary)' }}>{r.desc}</td>
                  <td style={{ textAlign: 'right', padding: '10px 6px', fontFamily: 'monospace', color: 'var(--text-muted)' }}>{r.impact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginTop: 14 }}>
          Total run differential is converted to win probability through a logistic curve: +1 expected run
          &#8776; +11% win probability. Final probabilities are capped at 5%-95% because no baseball game
          is ever a certainty.
        </p>
      </Card>

      {/* ============================================================ */}
      {/* Limitations */}
      {/* ============================================================ */}
      <Card>
        <CardTitle>Known Limitations</CardTitle>
        <ul style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, paddingLeft: 20 }}>
          <li><strong>No minor league data:</strong> Every rookie is underestimated until they build up an MLB track record.</li>
          <li><strong>No injury model:</strong> Playing time uses an age-based discount, not actual injury history or news.</li>
          <li><strong>League-wide platoon splits:</strong> We use average L/R multipliers, not batter-specific matchup data.</li>
          <li><strong>One lagged predictor:</strong> The OLS model does not directly see offseason trades or free agent signings (roster WAR catches some of this).</li>
          <li><strong>Static projections:</strong> Projections are computed once at startup. They do not update live during the day.</li>
        </ul>
      </Card>

      {/* ============================================================ */}
      {/* References */}
      {/* ============================================================ */}
      <Card style={{ marginBottom: 0 }}>
        <CardTitle>References</CardTitle>
        <ol style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.9, paddingLeft: 20 }}>
          <li>Tango, Lichtman & Dolphin (2006). <em>The Book: Playing the Percentages in Baseball.</em></li>
          <li>Lichtman, M. (2014). Aging curves in baseball. <em>The Hardball Times.</em></li>
          <li>Bradbury, J.C. (2010). Peak athletic performance and ageing. <em>Journal of Sports Sciences.</em></li>
          <li>Carleton, R. (2019). Statcast expected stats and projection blending. <em>Baseball Prospectus.</em></li>
          <li>Davenport, C. & Woolner, K. (1999). Pythagorean winning percentage. <em>Baseball Prospectus.</em></li>
          <li>James, B. (1981). <em>The Bill James Baseball Abstract.</em></li>
          <li>Miller, S. (2007). Year-over-year win persistence in MLB. <em>The Hardball Times.</em></li>
        </ol>
      </Card>
    </div>
  )
}
