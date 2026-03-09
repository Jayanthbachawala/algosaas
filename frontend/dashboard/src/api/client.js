const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8020'

export async function apiGet(path) {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

export async function apiPost(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

export function wsUrl(symbol) {
  const base = API_BASE.replace('http://', 'ws://').replace('https://', 'wss://')
  return `${base}/ws/market/${symbol}`
}
