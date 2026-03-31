import axios from 'axios'

const BACKEND = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${BACKEND}/api`,
  timeout: 120000,
})

export async function searchAll(query) {
  const { data } = await api.get('/search', { params: { q: query } })
  return data
}

export async function getStandings() {
  const { data } = await api.get('/standings')
  return data
}

export async function getTeam(teamId) {
  const { data } = await api.get(`/team/${teamId}`)
  return data
}

export async function getPlayer(playerId) {
  const { data } = await api.get(`/player/${playerId}`)
  return data
}

export async function getMatchups() {
  const { data } = await api.get('/matchups/today')
  return data
}

export async function getSeasonProjections() {
  const { data } = await api.get('/season/projections')
  return data
}

export async function getModelCoefficients() {
  const { data } = await api.get('/model/coefficients')
  return data
}

export async function getModelValidation() {
  const { data } = await api.get('/model/validation')
  return data
}

export default api
