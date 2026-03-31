import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Navbar from './components/Navbar'
import HomePage from './pages/HomePage'
import TeamPage from './pages/TeamPage'
import PlayerPage from './pages/PlayerPage'
import MatchupsPage from './pages/MatchupsPage'
import SeasonPage from './pages/SeasonPage'
import ModelPage from './pages/ModelPage'
import PrivacyPage from './pages/PrivacyPage'
import TermsPage from './pages/TermsPage'
import DisclaimerPage from './pages/DisclaimerPage'

function Footer() {
  return (
    <footer style={{
      borderTop: '1px solid var(--border)',
      padding: '24px 20px',
      marginTop: 48,
      textAlign: 'center',
      color: 'var(--text-muted)',
      fontSize: 13,
      lineHeight: 1.8,
    }}>
      <div style={{ maxWidth: 800, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginBottom: 12, flexWrap: 'wrap' }}>
          <Link to="/disclaimer" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Disclaimer</Link>
          <Link to="/terms" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Terms of Service</Link>
          <Link to="/privacy" style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Privacy Policy</Link>
        </div>
        <p style={{ marginBottom: 8 }}>
          Predictions are for entertainment only. Not gambling advice.
          See <Link to="/disclaimer" style={{ color: 'var(--text-secondary)', textDecoration: 'underline' }}>full disclaimer</Link>.
        </p>
        <p style={{ fontSize: 12, marginBottom: 8 }}>
          Not affiliated with Major League Baseball. MLB data via MLB Stats API and Lahman Database.
          Statcast data via Baseball Savant. Team names and logos are trademarks of their respective owners.
        </p>
        <p style={{ fontSize: 12 }}>
          &copy; {new Date().getFullYear()} Andrew Maxwell. All rights reserved.
        </p>
      </div>
    </footer>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <Navbar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/team/:teamId" element={<TeamPage />} />
            <Route path="/player/:playerId" element={<PlayerPage />} />
            <Route path="/matchups" element={<MatchupsPage />} />
            <Route path="/season" element={<SeasonPage />} />
            <Route path="/model" element={<ModelPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/disclaimer" element={<DisclaimerPage />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </BrowserRouter>
  )
}
