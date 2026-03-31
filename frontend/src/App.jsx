import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import HomePage from './pages/HomePage'
import TeamPage from './pages/TeamPage'
import PlayerPage from './pages/PlayerPage'
import MatchupsPage from './pages/MatchupsPage'
import SeasonPage from './pages/SeasonPage'
import ModelPage from './pages/ModelPage'

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
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
