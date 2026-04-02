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
  YES: '#22c55e',
}

const CONF_COLOR = {
  Strong: '#22c55e',
  Moderate: '#f97316',
  Lean: '#eab308',
  'No edge': 'var(--text-muted)',
}

const PROP_TYPE_LABEL = {
  strikeout: 'K',
  hits: 'H',
  home_run: 'HR',
  total_bases: 'TB',
  pitcher_strikeouts: 'P-K',
}

const PROP_TYPE_COLOR = {
  strikeout: '#ef4444',
  hits: '#3b82f6',
  home_run: '#f97316',
  total_bases: '#a855f7',
  pitcher_strikeouts: '#22c55e',
}

// Inject pulse animation
if (typeof document !== 'undefined' && !document.getElementById('edge-pulse-style')) {
  const style = document.createElement('style')
  style.id = 'edge-pulse-style'
  style.textContent = `@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }`
  document.head.appendChild(style)
}

function isGameStarted(gameTime) {
  if (!gameTime) return false
  return new Date(gameTime) < new Date()
}

function LiveBadge() {
  return (
    <span style={{
      background: '#ef444420',
      color: '#ef4444',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 10,
      fontWeight: 800,
      letterSpacing: 1,
      textTransform: 'uppercase',
      animation: 'pulse 2s infinite',
    }}>
      LIVE
    </span>
  )
}

function ContractPrice({ price, label }) {
  if (!price) return null
  const cents = Math.round(price * 100)
  const color = '#22c55e'
  return (
    <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
      <span style={{ color, fontSize: 15 }}>{cents}&cent;</span>
      {label && <span style={{ color: 'var(--text-muted)', fontWeight: 400, fontSize: 11, marginLeft: 4 }}>{label}</span>}
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

/* --- BET SLIP (Kalshi) --- */
function BetSlip({ slip }) {
  if (!slip || !slip.bets || slip.bets.length === 0) return null

  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(34,197,94,0.06), rgba(59,130,246,0.06))',
      border: '2px solid #22c55e30',
      borderRadius: 14,
      padding: 20,
      marginBottom: 24,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800 }}>
            <span style={{ marginRight: 8 }}>Kalshi Bet Slip</span>
            <span style={{
              background: '#3b82f620',
              color: '#3b82f6',
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.5,
              verticalAlign: 'middle',
            }}>PREDICTION MARKET</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            $100 bankroll &middot; Kelly-sized &middot; {slip.num_bets} contract{slip.num_bets !== 1 ? 's' : ''}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>TOTAL INVESTED</div>
          <div style={{ fontSize: 20, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)' }}>
            ${slip.total_wagered.toFixed(2)}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {slip.bets.map((bet, i) => {
          const started = isGameStarted(bet.game_time)
          const buyPriceCents = Math.round((bet.buy_price || 0) * 100)
          return (
          <div key={i} style={{
            background: 'var(--bg-surface)',
            border: `1px solid ${started ? '#ef444430' : 'var(--border)'}`,
            borderRadius: 10,
            padding: '12px 16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            opacity: started ? 0.6 : 1,
          }}>
            <div style={{ flex: '1 1 200px' }}>
              <div style={{ fontWeight: 700, fontSize: 15 }}>
                <span style={{ color: '#22c55e' }}>BUY YES</span>
                <span style={{ color: 'var(--text-primary)', marginLeft: 6 }}>{bet.team}</span>
                {started && <span style={{ marginLeft: 8 }}><LiveBadge /></span>}
              </div>
              <div style={{ fontSize: 12, color: started ? '#ef4444' : 'var(--text-muted)', marginTop: 2 }}>
                {bet.matchup} &middot;{' '}
                {new Date(bet.game_time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
                {started && ' (started)'}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ textAlign: 'center', minWidth: 55 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Price</div>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: 15, color: '#3b82f6' }}>
                  {buyPriceCents}&cent;
                </div>
              </div>
              <div style={{ textAlign: 'center', minWidth: 50 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Model</div>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, fontSize: 13 }}>
                  {(bet.model_prob * 100).toFixed(0)}%
                </div>
              </div>
              <div style={{ textAlign: 'center', minWidth: 50 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Edge</div>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, fontSize: 13, color: '#22c55e' }}>
                  +{bet.edge_pct}%
                </div>
              </div>
              <div style={{
                textAlign: 'center',
                minWidth: 70,
                background: '#22c55e15',
                borderRadius: 8,
                padding: '6px 12px',
              }}>
                <div style={{ fontSize: 10, color: '#22c55e', textTransform: 'uppercase', fontWeight: 700 }}>Invest</div>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 800, fontSize: 16, color: '#22c55e' }}>
                  ${bet.bet_amount.toFixed(2)}
                </div>
              </div>
              <div style={{ textAlign: 'center', minWidth: 60 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Profit</div>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: 14, color: 'var(--accent)' }}>
                  +${bet.potential_profit.toFixed(2)}
                </div>
              </div>
            </div>
          </div>
        )})}
      </div>

      {/* Summary footer */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginTop: 14,
        paddingTop: 14,
        borderTop: '1px solid var(--border)',
        fontSize: 13,
        flexWrap: 'wrap',
        gap: 12,
      }}>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>Remaining: </span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
            ${slip.remaining_bankroll.toFixed(2)}
          </span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>If all hit: </span>
          <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: '#22c55e' }}>
            +${slip.total_potential_profit.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  )
}

/* --- GAME CARD (Kalshi) --- */
function TodayGameCard({ game }) {
  const isPass = game.value_side === 'PASS'
  const started = isGameStarted(game.game_time)
  const homeCents = Math.round((game.kalshi_home_price || 0) * 100)
  const awayCents = Math.round((game.kalshi_away_price || 0) * 100)
  const valuePriceCents = Math.round((game.value_price || 0) * 100)

  return (
    <div
      style={{
        background: 'var(--bg-surface)',
        border: `1px solid ${started ? '#ef444440' : isPass ? 'var(--border)' : STRENGTH_COLOR[game.strength] + '40'}`,
        borderRadius: 10,
        padding: 16,
        opacity: started ? 0.65 : 1,
      }}
    >
      {started && (
        <div style={{
          background: '#ef444410',
          border: '1px solid #ef444430',
          borderRadius: 6,
          padding: '6px 12px',
          marginBottom: 10,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          fontSize: 12,
          color: '#ef4444',
          fontWeight: 600,
        }}>
          <LiveBadge /> Game has started — contract prices may have changed significantly
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700 }}>
            {game.away_team} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>@</span> {game.home_team}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {new Date(game.game_time).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
            {started && <span style={{ color: '#ef4444' }}> (started)</span>}
            {game.kalshi_volume > 0 && <span> &middot; Vol: {game.kalshi_volume}</span>}
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
                BUY YES {game.value_team} ({game.value_side})
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Contract Price</div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: 18, color: '#3b82f6' }}>
                {valuePriceCents}&cent;
              </div>
            </div>
          </div>
        </div>
      )}

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
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 4 }}>KALSHI MARKET</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'JetBrains Mono, monospace' }}>
            <span>{game.away_team.split(' ').pop()} {awayCents}&cent;</span>
            <span>{game.home_team.split(' ').pop()} {homeCents}&cent;</span>
          </div>
          <div style={{ display: 'flex', height: 4, borderRadius: 2, overflow: 'hidden', background: 'var(--border)', marginTop: 4 }}>
            <div style={{ width: `${(game.kalshi_away_price || 0) * 100}%`, background: '#3b82f6' }} />
            <div style={{ width: `${(game.kalshi_home_price || 0) * 100}%`, background: '#22c55e' }} />
          </div>
        </div>
      </div>

      {game.kalshi_ticker && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, textAlign: 'right' }}>
          {game.kalshi_ticker}
        </div>
      )}
    </div>
  )
}

/* --- PLAYER PROP CARD --- */
function PropCard({ prop }) {
  const typeColor = PROP_TYPE_COLOR[prop.type] || 'var(--text-muted)'
  const typeLabel = PROP_TYPE_LABEL[prop.type] || prop.type
  const started = isGameStarted(prop.game_time)

  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: `1px solid ${started ? '#ef444430' : typeColor + '30'}`,
      borderRadius: 10,
      padding: '14px 16px',
      opacity: started ? 0.65 : 1,
    }}>
      {started && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          marginBottom: 8,
          fontSize: 11,
          color: '#ef4444',
          fontWeight: 600,
        }}>
          <LiveBadge /> Game started
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{
              background: `${typeColor}20`,
              color: typeColor,
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: 0.5,
            }}>
              {typeLabel}
            </span>
            <span style={{ fontSize: 15, fontWeight: 700 }}>{prop.player}</span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {prop.player_team} &middot; {prop.matchup}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <span style={{ color: CONF_COLOR[prop.confidence], fontSize: 12, fontWeight: 700 }}>
            {prop.confidence}
          </span>
          <div style={{
            fontFamily: 'JetBrains Mono, monospace',
            fontSize: 11,
            color: 'var(--text-muted)',
            marginTop: 2,
          }}>
            {prop.confidence_score}/100
          </div>
        </div>
      </div>

      <div style={{
        background: `${typeColor}08`,
        border: `1px solid ${typeColor}20`,
        borderRadius: 8,
        padding: '8px 12px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 800, color: typeColor }}>
            {prop.recommendation} {prop.line} {prop.type === 'home_run' ? '' : prop.type === 'pitcher_strikeouts' ? 'Ks' : prop.type.replace('_', ' ')}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            Projected: <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>{prop.projected_value}</span>
          </div>
        </div>
      </div>

      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.5 }}>
        {prop.reasoning}
      </div>
    </div>
  )
}

/* --- SEASON EDGE ROW --- */
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

/* --- MAIN PAGE --- */
export default function EdgePage() {
  const [tab, setTab] = useState('today')
  const [todayData, setTodayData] = useState(null)
  const [seasonData, setSeasonData] = useState(null)
  const [propsData, setPropsData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [propsFilter, setPropsFilter] = useState('all')

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError(null)
      try {
        if (tab === 'today') {
          const { data } = await api.get('/edge/today')
          setTodayData(data)
        } else if (tab === 'props') {
          const { data } = await api.get('/edge/props')
          setPropsData(data)
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

  const filteredProps = propsData?.props?.filter(p =>
    propsFilter === 'all' || p.type === propsFilter
  ) || []

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 800, marginBottom: 4 }}>
          Edge Finder
          <span style={{
            background: '#3b82f620',
            color: '#3b82f6',
            padding: '3px 10px',
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: 0.5,
            marginLeft: 10,
            verticalAlign: 'middle',
          }}>KALSHI</span>
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          Model vs Kalshi prediction market &mdash; find contracts where the model disagrees with consumer-set prices.
          Buy YES when our model says the true probability is higher than the contract price.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, flexWrap: 'wrap' }}>
        {[
          { key: 'today', label: "Today's Games" },
          { key: 'props', label: 'Player Props' },
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
          Loading...
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
          {todayData.bet_slip && <BetSlip slip={todayData.bet_slip} />}

          <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
            {[
              { label: 'Games', value: todayData.total_games },
              { label: 'Value Contracts', value: todayData.value_bets, color: '#22c55e' },
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
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {todayData.games.map((game, i) => (
              <TodayGameCard key={i} game={game} />
            ))}
          </div>

          {todayData.games.length === 0 && (
            <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
              {todayData.message || 'No Kalshi markets found for today\'s MLB games.'}
            </div>
          )}

          {todayData.kalshi_status && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 12, textAlign: 'right' }}>
              {todayData.kalshi_status}
            </div>
          )}
        </>
      )}

      {/* PROPS TAB */}
      {!loading && !error && tab === 'props' && propsData && (
        <>
          {propsData.bet_slip && propsData.bet_slip.bets.length > 0 && (
            <div style={{
              background: 'linear-gradient(135deg, rgba(168,85,247,0.06), rgba(59,130,246,0.06))',
              border: '2px solid #a855f730',
              borderRadius: 14,
              padding: 20,
              marginBottom: 24,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 18, fontWeight: 800 }}>Props Bet Slip</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    $100 bankroll &middot; {propsData.bet_slip.num_bets} prop{propsData.bet_slip.num_bets !== 1 ? 's' : ''} &middot; confidence-weighted
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>TOTAL WAGERED</div>
                  <div style={{ fontSize: 20, fontWeight: 800, fontFamily: 'JetBrains Mono, monospace', color: '#a855f7' }}>
                    ${propsData.bet_slip.total_wagered.toFixed(2)}
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {propsData.bet_slip.bets.map((bet, i) => {
                  const typeColor = PROP_TYPE_COLOR[bet.type] || 'var(--text-muted)'
                  const typeLabel = PROP_TYPE_LABEL[bet.type] || bet.type
                  return (
                    <div key={i} style={{
                      background: 'var(--bg-surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 10,
                      padding: '10px 14px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 10,
                      flexWrap: 'wrap',
                    }}>
                      <div style={{ flex: '1 1 220px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{
                            background: `${typeColor}20`,
                            color: typeColor,
                            padding: '1px 6px',
                            borderRadius: 3,
                            fontSize: 10,
                            fontWeight: 700,
                          }}>{typeLabel}</span>
                          <span style={{ fontWeight: 700, fontSize: 14 }}>{bet.player}</span>
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                          {bet.prop} &middot; {bet.matchup}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                        <div style={{ textAlign: 'center', minWidth: 45 }}>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>PROJ</div>
                          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600, fontSize: 13 }}>
                            {bet.projected_value}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', minWidth: 45 }}>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>ODDS</div>
                          <MoneylineTag ml={bet.est_odds} />
                        </div>
                        <div style={{
                          textAlign: 'center',
                          minWidth: 60,
                          background: '#a855f715',
                          borderRadius: 8,
                          padding: '4px 10px',
                        }}>
                          <div style={{ fontSize: 10, color: '#a855f7', fontWeight: 700 }}>BET</div>
                          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 800, fontSize: 15, color: '#a855f7' }}>
                            ${bet.bet_amount.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', minWidth: 50 }}>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>WIN</div>
                          <div style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, fontSize: 13, color: '#22c55e' }}>
                            +${bet.potential_profit.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginTop: 14,
                paddingTop: 14,
                borderTop: '1px solid var(--border)',
                fontSize: 13,
                flexWrap: 'wrap',
                gap: 12,
              }}>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>Remaining: </span>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 600 }}>
                    ${propsData.bet_slip.remaining_bankroll.toFixed(2)}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>If all hit: </span>
                  <span style={{ fontFamily: 'JetBrains Mono, monospace', fontWeight: 700, color: '#22c55e' }}>
                    +${propsData.bet_slip.total_potential_profit.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: '10px 16px',
              fontSize: 13,
            }}>
              <span style={{ color: 'var(--text-muted)' }}>Total Props: </span>
              <span style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace' }}>
                {propsData.total_props}
              </span>
            </div>
            <div style={{
              background: 'var(--bg-surface)',
              border: '1px solid #22c55e30',
              borderRadius: 8,
              padding: '10px 16px',
              fontSize: 13,
            }}>
              <span style={{ color: 'var(--text-muted)' }}>Strong: </span>
              <span style={{ fontWeight: 700, fontFamily: 'JetBrains Mono, monospace', color: '#22c55e' }}>
                {propsData.strong_props}
              </span>
            </div>
          </div>

          {/* Filter buttons */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              { key: 'all', label: 'All' },
              { key: 'pitcher_strikeouts', label: 'Pitcher Ks', color: PROP_TYPE_COLOR.pitcher_strikeouts },
              { key: 'strikeout', label: 'Batter Ks', color: PROP_TYPE_COLOR.strikeout },
              { key: 'hits', label: 'Hits', color: PROP_TYPE_COLOR.hits },
              { key: 'home_run', label: 'Home Runs', color: PROP_TYPE_COLOR.home_run },
              { key: 'total_bases', label: 'Total Bases', color: PROP_TYPE_COLOR.total_bases },
            ].map(f => (
              <button
                key={f.key}
                onClick={() => setPropsFilter(f.key)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 6,
                  fontSize: 12,
                  fontWeight: propsFilter === f.key ? 700 : 400,
                  color: propsFilter === f.key ? (f.color || 'var(--accent)') : 'var(--text-secondary)',
                  background: propsFilter === f.key ? `${f.color || 'var(--accent)'}15` : 'transparent',
                  border: `1px solid ${propsFilter === f.key ? (f.color || 'var(--accent)') + '50' : 'var(--border)'}`,
                  cursor: 'pointer',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: 12 }}>
            {filteredProps.map((prop, i) => (
              <PropCard key={i} prop={prop} />
            ))}
          </div>

          {filteredProps.length === 0 && (
            <div style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
              {propsData.message || 'No player props available for today\'s games.'}
            </div>
          )}
        </>
      )}

      {/* SEASON TAB */}
      {!loading && !error && tab === 'season' && seasonData && (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 20 }}>
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

      {/* How Kalshi Works */}
      {tab === 'today' && (
        <div style={{
          marginTop: 24,
          padding: 16,
          background: 'rgba(59,130,246,0.05)',
          border: '1px solid rgba(59,130,246,0.2)',
          borderRadius: 8,
          fontSize: 12,
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
        }}>
          <strong style={{ color: '#3b82f6' }}>How Kalshi Works:</strong> Kalshi is a prediction market where contract prices = implied probabilities.
          A contract at 55&cent; means the market thinks there's a 55% chance. If our model says 62%, that's a 7% edge &mdash; buy YES.
          Each contract pays $1 if correct, $0 if wrong. Prices are set by consumers, not quants, so there are more inefficiencies to exploit.
        </div>
      )}

      <div style={{
        marginTop: 16,
        padding: 16,
        background: 'rgba(239,68,68,0.05)',
        border: '1px solid rgba(239,68,68,0.2)',
        borderRadius: 8,
        fontSize: 12,
        color: 'var(--text-secondary)',
        lineHeight: 1.6,
      }}>
        <strong style={{ color: '#ef4444' }}>Disclaimer:</strong> This tool is for research and entertainment purposes only.
        Not gambling advice. Past model performance does not guarantee future results. Trade responsibly.
      </div>
    </div>
  )
}
