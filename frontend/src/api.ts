import type { Model } from './types'

const API_BASE = 'http://127.0.0.1:15801/api'

async function fetchWithRetry(url: string, options?: RequestInit, retries = 3): Promise<Response> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url, { ...options, mode: 'cors' })
      if (res.ok) return res
    } catch (e) {
      console.warn(`Fetch attempt ${i + 1} failed:`, e)
      if (i === retries - 1) throw e
      await new Promise(r => setTimeout(r, 500 * (i + 1)))
    }
  }
  throw new Error('Max retries exceeded')
}

export async function getConfig() {
  const res = await fetchWithRetry(`${API_BASE}/config`)
  return res.json()
}

export async function saveConfig(config: Record<string, unknown>) {
  const res = await fetchWithRetry(`${API_BASE}/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  return res.json()
}

export async function getModels() {
  const res = await fetchWithRetry(`${API_BASE}/models`)
  return res.json() as Promise<Model[]>
}

export async function saveModels(models: Model[]) {
  const res = await fetchWithRetry(`${API_BASE}/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(models),
  })
  return res.json()
}

export async function enableModel(idx: number) {
  const res = await fetchWithRetry(`${API_BASE}/models/${idx}/enable`, { method: 'POST' })
  return res.json()
}

export async function deleteModel(idx: number) {
  const res = await fetchWithRetry(`${API_BASE}/models/${idx}`, { method: 'DELETE' })
  return res.json()
}

export async function getLogs() {
  const res = await fetchWithRetry(`${API_BASE}/logs`)
  return res.json()
}

export async function getStatus() {
  const res = await fetchWithRetry(`${API_BASE}/status`)
  return res.json()
}

export async function startProxy() {
  const res = await fetchWithRetry(`${API_BASE}/proxy/start`, { method: 'POST' })
  return res.json()
}

export async function stopProxy() {
  const res = await fetchWithRetry(`${API_BASE}/proxy/stop`, { method: 'POST' })
  return res.json()
}

export async function toggleAutostart(enabled: boolean) {
  const res = await fetchWithRetry(`${API_BASE}/autostart`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  return res.json()
}
