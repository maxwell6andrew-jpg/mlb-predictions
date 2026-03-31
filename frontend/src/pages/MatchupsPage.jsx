import { useState, useEffect } from 'react'
import { getMatchups } from '../api/client'

const WIN_PROB_COLOR = (prob) => {
  if (prob >= 0.65) return 'var(--positive)'
  if (prob >= 0.55) return 'var(--accent)'
  return 'var(--text-secondary)'
}

const CONFIDENCE_COLOR = {
  Strong: 'var(--positive)',
  Moderate: 'var(--accent)',
  'Toss-up': 'var(--text-muted)',
}

const IMPACT_COLOR = {
  high: '#a855f7',
  medium: 'var(--accent)',
  low: 'var(--text-muted)',
}

function WinProbBar({ homeProb, homeName, awayName }) {
  const away = 1 - homeProb
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4, color: 'var(--text-secondary)' }}>
        <span>{awayName}</span>
        <span>{homeName}</span>
      </div>
      <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', background: 'var(--border)' }}>
        <div style={{ width: `${away * 100}%`, background: '#ef4444', transition: 'width 0.5s' }} />
        <div style={{ width: `${homeProb * 100}%`, background: '#22c55e', transition: 'width 0.5s' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginTop: 4, fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
        <span style={{ color: '#ef4444' }}>{(away * 100).toFixed(0)}%</span>
        <span style={{ color: '#22c55e' }}>{(homeProb * 100).toFixed(0)}%</span>
      </div>
    </div>
  )
}

function GameCard({ game }) {
  const [expanded, setExpanded] = useState(false)
  const isHome = game.home_win_prob >= 0.5
  const winner = isHome ? game.home_team_name : game.away_team_name
  const winnerProb = isHome ? game.home_win_prob : game.away_win_prob

  return (
    <div className="card" style={{ cursor: 'pointer' }} onClick={() => setExpanded(e => !e)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700 }}>
            {game.away_team_name} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>@</span> {game.home_team_name}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {game.away_sp} vs {game.home_sp}
            {game.away_fip && game.home_fip && (
              <span style={{ marginLeft: 8, fontFamily: 'JetBrains Mono, monospace' }}>
                FIP: {game.away_fip} / {game.home_fip}
              </span>
            )}
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: WIN_PROB_COLOR(winnerProb) }}>
            {winner} {(winnerProb * 100).toFixed(0)}%
          </div>
          <div style={{ fontSize: 12, color: CONFIDENCE_COLOR[game.confidence] || 'var(--text-muted)' }}>
            {game.confidence} · {game.game_status}
          </div>
        </div>
      </div>

      <WinProbBar
        homeProb={game.home_win_prob}
        homeName={game.home_team_name}
        awayName={game.away_team_name}
      />

      {expanded && game.factors?.length > 0 && (
        <div style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--text-muted)', marginBottom: 8 }}>
            Key Factors
          </div>
          {game.factors.map((f, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <div>
                <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{f.factor}</span>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)', marginLeft: 8 }}>{f.direction}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 13, fontFamily: 'JetBrains Mono, monospace', color: 'var(--text-primary)' }}>
                  {f.value}
                </span>
                <span style={{
                  fontSize: 10,
                  padding: '2px 6px',
                  borderRadius: 4,
                  background: `${IMPACT_COLOR[f.impact]}20`,
                  color: IMPACT_COLOR[f.impact],
                  fontWeight: 600,
                  textTransform: 'uppercase',
                }}>
                  {f.impact}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
        {expanded ? '▲ collapse' : '▼ show factors'}
      </div>
    </div>
  )
}

export default function MatchupsPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getMatchups()
      .then(setData)
      .catch(err => setError(err.response?.data?.detail || err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading today's matchups</div>
  if (error) return <div className="error">Failed to load matchups: {error}</div>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 800 }}>
            Today's <span style={{ color: 'var(--accent)' }}>Matchups</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 4 }}>
            {data?.date} · {data?.total_games} games · Sorted by win probability differential
          </p>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'right' }}>
          Updated<br />{data?.last_updated}
        </div>
      </div>

      {data?.games?.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-secondary)' }}>
          No games scheduled today
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(460px, 1fr))', gap: 14 }}>
        {data?.games?.map(game => (
          <GameCard key={game.game_id} game={game} />
        ))}
      </div>

      <div style={{ marginTop: 20, fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
        Win probabilities use log5 formula with SP FIP, team OPS differential, bullpen ERA, and home field advantage. Click a card to expand factors.
      </div>
    </div>
  )
}
