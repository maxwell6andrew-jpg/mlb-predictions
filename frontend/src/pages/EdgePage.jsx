import { useState, useEffect } from 'react'
import api from '../api/client'

const STRENGTH_COLOR = {
  STRONG: '#22c55e',
  MODERATE: '#f97316',
  SLIGHT: '#eab308',
  'NO EDGE': 'var(--text-muted)',
}

const SIDE_COLOR = {
  HOME: '#22c55e',
  AWAY: '#3b82f6',
  PASS: 'var(--text-muted)',
  OVER: '#22c55e',
  UNDER: '#ef4444',
}

const CONF_COLOR = {
  Strong: '#22c55e',
  Moderate: '#f97316',
  Lean: '#eab308',
  'No edge': 'var(--text-muted)',
}

function MoneylineTag({ ml, book }) {
  if (!ml) return null
  const color = ml > 0 ? '#22c55e' : '#ef4444'
  return (
    <span style={{ fontFamily: 'JetBrains Mono, monospace', color, fontWeight: 600 }}>
      {ml > 0 ? '+' : ''}{ml}
      {book && <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11, marginLeft: 4 }}>{book}</span>}
    </span>
  )
}

function EVBadge({ ev }) {
  const color = ev > 5 ? '#22c55e' : ev > 2 ? '#f97316' : ev > 0 ? '#eab308' : '#ef4444'
  return (
    <span style={{
      fontFamily: 'JetBrains Mono, monospace',
      fontWeight: 700,
      color,
      background: `${color}15`,
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 14,
    }}>
      {ev > 0 ? '+' : ''}{ev.toFixed(2)}
    </span>
  )
}

function TodayGameCard({ game }) {
  const [expanded, setExpanded] = useState(false)
  const isPass = game.value_side === 'PASS'

  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${isPass ? 'var(--border)' : STRENGTH_COLOR[game.strength] + '40'}`,
        borderRadius: 10,
        padding: 16,
        cursor: 'pointer',
      }}
      onClick={() => setExpanded(e => !e)}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700 }}>
            {game.away_team} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>@</span> {game.home_team}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {new Date(game.game_time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
            {game.game_total && <span> &middot; O/U {game.game_total}</span>}
            <span> &middot; {game.num_books} books</span>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          {!isPass ? (
            <>
              <div style={{
                fontSize: 13,
                fontWeight: 700,
                color: STRENGTH_COLOR[game.strength],
                textTransform: 'uppercase',
                letterSpacing: 0.5,
              }}>
                {game.strength}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                EV: <EVBadge ev={game.ev_per_100} /> / $100
              </div>
            </>
          ) : (
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>NO EDGE</div>
          )}
        </div>
      </div>

      {/* Value Pick */}
      {!isPass && (
        <div style={{
          background: `${SIDE_COLOR[game.value_side]}10`,
          border: `1px solid ${SIDE_COLOR[game.value_side]}30`,
          borderRadius: 8,
          padding: '10px 14px',
          marginBottom: 12,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>VALUE PICK</span>
              <div style={{ fontSize: 16, fontWeight: 700, color: SIDE_COLOR[game.value_side], marginTop: 2 }}>
                {game.value_team} ({game.value_side})
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Best Line</div>
              <MoneylineTag ml={game.value_side === 'HOME' ? game.best_home_ml : game.best_away_ml} book={game.best_book} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 20, marginTop: 10, fontSize: 13 }}>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Edge: </span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, color: game.edge_pct > 0 ? '#22c55e' : '#ef4444' }}>
                {game.edge_pct > 0 ? '+' : ''}{game.edge_pct}%
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Kelly: </span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                {game.kelly_pct.toFixed(1)}%
              </span>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Bet/$100: </span>
              <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: 'var(--accent)' }}>
                ${game.kelly_bet_on_100.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Probability Comparison */}
      <div style={{ display: 'flex', gap: 12, fontSize: 13 }}>
        <div style={{ flex: 1 }}>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 4 }}>MODEL</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'JetBrains Mono, monospace' }}>
            <span>{game.away_team.split(' ').pop()} {(game.model_away_prob * 100).toFixed(0)}%</span>
            <span>{game.home_team.split(' ').pop()} {(game.model_home_prob * 100).toFixed(0)}%</span>
          </div>
          <div style={{ display: 'flex', height: 4, borderRadius: 2, overflow: 'hidden', background: 'var(--border)', marginTop: 4 }}>
            <div style={{ width: `${game.model_away_prob * 100}%`, background: '#3b82f6' }} />
            <div style={{ width: `${game.model_home_prob * 100}%`, background: '#22c55e' }} />
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 4 }}>VEGAS (no-vig)</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'JetBrains Mono, monospace' }}>
            <span>{game.away_team.split(' ').pop()} {(game.vegas_away_prob * 100).toFixed(0)}%</span>
            <span>{game.home_team.split(' ').pop()} {(game.vegas_home_prob * 100).toFixed(0)}%</span>
          </div>
          <div style={{ display: 'flex', height: 4, borderRadius: 2, overflow: 'hidden', background: 'var(--border)', marginTop: 4 }}>
            <div style={{ width: `${game.vegas_away_prob * 100}%`, background: '#3b82f6' }} />
            <div style={{ width: `${game.vegas_home_prob * 100}%`, background: '#22c55e' }} />
          </div>
        </div>
      </div>

      {/* Expanded: All odds */}
      {expanded && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
            All Sportsbook Lines
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
            {game.all_odds.map((o, i) => (
              <div key={i} style={{
                background: 'var(--bg-card)',
                borderRadius: 6,
                padding: '8px 12px',
                fontSize: 13,
              }}>
                <div style={{ fontWeight: 600, textTransform: 'capitalize', marginBottom: 4, fontSize: 12 }}>
                  {o.book.replace(/([a-z])([A-Z])/g, '$1 $2')}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'JetBrains Mono, monospace' }}>
                  <MoneylineTag ml={o.away_ml} />
                  <MoneylineTag ml={o.home_ml} />
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
            <div style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Model ML: </span>
              <MoneylineTag ml={game.model_away_ml} /> / <MoneylineTag ml={game.model_home_ml} />
            </div>
            <div style={{ fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>Consensus: </span>
              <MoneylineTag ml={game.vegas_away_ml} /> / <MoneylineTag ml={game.vegas_home_ml} />
            </div>
          </div>
        </div>
      )}

      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, textAlign: 'right' }}>
        {expanded ? 'click to collapse' : 'click for all lines'}
      </div>
    </div>
  )
}

function SeasonEdgeRow({ edge }) {
  const isPass = edge.recommendation === 'PASS'
  const color = SIDE_COLOR[edge.recommendation] || 'var(--text-muted)'

  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{edge.abbreviation}</td>
      <td style={{ padding: '10px 8px' }}>{edge.name}</td>
      <td style={{ padding: '10px 8px', fontFamily: 'JetBrains Mono, monospace', textAlign: 'center' }}>
        {edge.model_wins.toFixed(1)}
      </td>
      <td style={{ padding: '10px 8px', fontFamily: 'JetBrains Mono, monospace', textAlign: 'center' }}>
        {edge.vegas_wins}
      </td>
      <td style={{
        padding: '10px 8px',
        fontFamily: 'JetBrains Mono, monospace',
        textAlign: 'center',
        fontWeight: 700,
        color: edge.difference > 0 ? '#22c55e' : edge.difference < 0 ? '#ef4444' : 'var(--text-muted)',
      }}>
        {edge.difference > 0 ? '+' : ''}{edge.difference}
      </td>
      <td style={{ padding: '10px 8px', textAlign: 'center' }}>
        {!isPass ? (
          <span style={{
            background: `${color}20`,
            color,
            padding: '3px 10px',
            borderRadius: 4,
            fontWeight: 700,
            fontSize: 12,
          }}>
            {edge.recommendation}
          </span>
        ) : (
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>-</span>
        )}
      </td>
      <td style={{ padding: '10px 8px', textAlign: 'center' }}>
        <span style={{ color: CONF_COLOR[edge.confidence] || 'var(--text-muted)', fontSize: 12, fontWeight: 600 }}>
          {edge.confidence}
        </span>
      </td>
    </tr>
  )
}

export default function EdgePage() {
  const [tab, setTab] = useState('today')
  const [todayData, setTodayData] = useState(null)
  const [seasonData, setSeasonData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError(null)
      try {
        if (tab === 'today') {
          const { data } = await api.get('/edge/today')
          setTodayData(data)
        } else {
          const { data } = await api.get('/edge/season')
          setSeasonData(data)
        }
      } catch (err) {
        setError(err.response?.data?.detail || err.message)
      }
      setLoading(false)
    }
    load()
  }, [tab])

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>
          Edge Finder
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          Model vs Vegas &mdash; find value where the model disagrees with the market.
          For research/entertainment only.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {[
          { key: 'today', label: "Today's Games" },
          { key: 'season', label: 'Season Totals' },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: '8px 20px',
              borderRadius: 6,
              fontSize: 14,
              fontWeight: tab === t.key ? 700 : 400,
              color: tab === t.key ? 'var(--accent)' : 'var(--text-secondary)',
              background: tab === t.key ? 'rgba(249,115,22,0.1)' : 'transparent',
              border: '1px solid ' + (tab === t.key ? 'var(--accent)' : 'var(--border)'),
              cursor: 'pointer',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
          Loading odds data...
        </div>
      )}

      {error && (
        <div style={{ textAlign: 'center', padding: 48, color: '#ef4444' }}>
          {error}
        </div>
      )}

      {/* TODAY TAB */}
      {!loading && !error && tab === 'today' && todayData && (
        <>
          {/* Summary bar */}
          <div style={{
            display: 'flex',
            gap: 16,
            marginBottom: 20,
            flexWrap: 'wrap',
          }}>
            {[
              { label: 'Games', value: todayData.total_games },
              { label: 'Value Bets', value: todayData.value_bets, color: '#22c55e' },
              { label: 'Date', value: todayData.date },
            ].map((s, i) => (
              <div key={i} style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 16px',
                fontSize: 13,
              }}>
                <span style={{ color: 'var(--text-muted)' }}>{s.label}: </span>
                <span style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: s.color || 'var(--text-primary)' }}>
                  {s.value}
                </span>
              </div>
            ))}
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '10px 16px',
              fontSize: 12,
              color: 'var(--text-muted)',
            }}>
              {todayData.quota}
            </div>
          </div>

          {/* Best bet highlight */}
          {todayData.best_bet && (
            <div style={{
              background: 'linear-gradient(135deg, rgba(34,197,94,0.08), rgba(249,115,22,0.08))',
              border: '2px solid #22c55e40',
              borderRadius: 12,
              padding: 20,
              marginBottom: 20,
            }}>
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5, color: '#22c55e', fontWeight: 700, marginBottom: 8 }}>
                Best Bet of the Day
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 800 }}>
                    {todayData.best_bet.value_team}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {todayData.best_bet.away_team} @ {todayData.best_bet.home_team}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>EV/$100</div>
                    <EVBadge ev={todayData.best_bet.ev_per_100} />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Best Line</div>
                    <MoneylineTag
                      ml={todayData.best_bet.value_side === 'HOME' ? todayData.best_bet.best_home_ml : todayData.best_bet.best_away_ml}
                      book={todayData.best_bet.best_book}
                    />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Kelly Bet</div>
                    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: 'var(--accent)', fontSize: 14 }}>
                      ${todayData.best_bet.kelly_bet_on_100.toFixed(2)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Game cards */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {todayData.games.map((game, i) => (
              <TodayGameCard key={i} game={game} />
            ))}
          </div>

          {todayData.games.length === 0 && (
            <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
              {todayData.message || 'No games with odds available today.'}
            </div>
          )}
        </>
      )}

      {/* SEASON TAB */}
      {!loading && !error && tab === 'season' && seasonData && (
        <>
          <div style={{
            display: 'flex',
            gap: 16,
            marginBottom: 20,
          }}>
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '10px 16px',
              fontSize: 13,
            }}>
              <span style={{ color: 'var(--text-muted)' }}>Value Bets: </span>
              <span style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: '#22c55e' }}>
                {seasonData.value_bets}
              </span>
              <span style={{ color: 'var(--text-muted)' }}> / 30 teams</span>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--border)' }}>
                  <th style={{ padding: '10px 12px', textAlign: 'left', fontSize: 12, color: 'var(--text-muted)' }}>Team</th>
                  <th style={{ padding: '10px 8px', textAlign: 'left', fontSize: 12, color: 'var(--text-muted)' }}>Name</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>Model W</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>Vegas W</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>Diff</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>Pick</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center', fontSize: 12, color: 'var(--text-muted)' }}>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {seasonData.season.map((edge, i) => (
                  <SeasonEdgeRow key={i} edge={edge} />
                ))}
              </tbody>
            </table>
          </div>

          <div style={{
            marginTop: 16,
            padding: 12,
            background: 'var(--bg-surface)',
            borderRadius: 8,
            fontSize: 12,
            color: 'var(--text-muted)',
            lineHeight: 1.6,
          }}>
            <strong>Methodology:</strong> {seasonData.methodology}
          </div>
        </>
      )}

      <div style={{
        marginTop: 32,
        padding: 16,
        background: 'rgba(239,68,68,0.05)',
        border: '1px solid rgba(239,68,68,0.2)',
        borderRadius: 8,
        fontSize: 12,
        color: 'var(--text-secondary)',
        lineHeight: 1.6,
      }}>
        <strong style={{ color: '#ef4444' }}>Disclaimer:</strong> This tool is for research and entertainment purposes only.
        Not gambling advice. Past model performance does not guarantee future results. Gamble responsibly.
      </div>
    </div>
  )
}
