import type { CodexAccountsStatus, CodexConfigStatus, CodexLauncherStatus, Config, LogEntry, Model } from './types'

const API_BASE = 'http://127.0.0.1:15801/api'
const LOCAL_APP_HEADER = { 'X-AI-Proxy-Manager': '1' }

async function fetchWithRetry(url: string, options?: RequestInit, retries = 3): Promise<Response> {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url, { ...options, mode: 'cors' })
      if (res.ok) return res
      // 4xx: client error, don't retry; 5xx: server error, retry
      if (res.status < 500) return res
      throw new Error(`HTTP ${res.status}`)
    } catch (e) {
      if (i === retries - 1) throw e
      await new Promise(r => setTimeout(r, 500 * (i + 1)))
    }
  }
  throw new Error('Max retries exceeded')
}

async function readJson<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}))
  const maybeError = data as { status?: string; message?: string; error?: unknown }
  if (!res.ok || maybeError.status === 'error') {
    const message = maybeError.message || (typeof maybeError.error === 'string' ? maybeError.error : `HTTP ${res.status}`)
    throw new Error(message)
  }
  return data as T
}

function withLocalHeader(options: RequestInit = {}): RequestInit {
  return {
    ...options,
    headers: {
      ...LOCAL_APP_HEADER,
      ...(options.headers || {}),
    },
  }
}

export async function getConfig() {
  const res = await fetchWithRetry(`${API_BASE}/config`)
  return readJson<Config>(res)
}

export async function saveConfig(config: Config | Record<string, unknown>) {
  const res = await fetchWithRetry(`${API_BASE}/config`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  }))
  return readJson<{ status: string; message?: string }>(res)
}

export async function getModels() {
  const res = await fetchWithRetry(`${API_BASE}/models`)
  return readJson<Model[]>(res)
}

export async function saveModels(models: Model[]) {
  const res = await fetchWithRetry(`${API_BASE}/models`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(models),
  }))
  return readJson<{ status: string; message?: string }>(res)
}

export async function enableModel(idx: number) {
  const res = await fetchWithRetry(`${API_BASE}/models/${idx}/enable`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string }>(res)
}

export async function deleteModel(idx: number) {
  const res = await fetchWithRetry(`${API_BASE}/models/${idx}`, withLocalHeader({ method: 'DELETE' }))
  return readJson<{ status: string; message?: string }>(res)
}

export async function getLogs() {
  const res = await fetchWithRetry(`${API_BASE}/logs`)
  return readJson<LogEntry[]>(res)
}

export async function getStatus() {
  const res = await fetchWithRetry(`${API_BASE}/status`)
  return readJson<{ running: boolean; autostart: boolean }>(res)
}

export async function startProxy() {
  const res = await fetchWithRetry(`${API_BASE}/proxy/start`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string; port?: number }>(res)
}

export async function stopProxy() {
  const res = await fetchWithRetry(`${API_BASE}/proxy/stop`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string }>(res)
}

export async function toggleAutostart(enabled: boolean) {
  const res = await fetchWithRetry(`${API_BASE}/autostart`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  }))
  return readJson<{ status: string; message?: string }>(res)
}

export async function getCodexConfigStatus() {
  const res = await fetchWithRetry(`${API_BASE}/codex-config/status`)
  return readJson<CodexConfigStatus>(res)
}

export async function applyProxyCodexConfig(port: number, model?: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-config/proxy`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port, model }),
  }))
  return readJson<{ status: string; message?: string; codex?: CodexConfigStatus }>(res)
}

export async function applyPureApiCodexConfig(port: number, model?: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-config/pure-api`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ port, model }),
  }))
  return readJson<{ status: string; message?: string; codex?: CodexConfigStatus }>(res)
}

export async function applyOfficialCodexConfig() {
  const res = await fetchWithRetry(`${API_BASE}/codex-config/official`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string; codex?: CodexConfigStatus }>(res)
}

export async function getCodexLauncherStatus() {
  const res = await fetchWithRetry(`${API_BASE}/codex-launcher/status`)
  return readJson<CodexLauncherStatus>(res)
}

export async function launchCodexWithUnlocks(terminateExisting = false) {
  const res = await fetchWithRetry(`${API_BASE}/codex-launcher/launch`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ terminate_existing: terminateExisting }),
  }))
  return readJson<{ status: string; message?: string; launcher?: CodexLauncherStatus }>(res)
}

export async function stopCodexProcesses() {
  const res = await fetchWithRetry(`${API_BASE}/codex-launcher/stop`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string; launcher?: CodexLauncherStatus }>(res)
}

export async function injectCodexUnlocks() {
  const res = await fetchWithRetry(`${API_BASE}/codex-launcher/inject`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string; launcher?: CodexLauncherStatus }>(res)
}

export async function getCodexAccounts() {
  const res = await fetchWithRetry(`${API_BASE}/codex-accounts`)
  return readJson<CodexAccountsStatus>(res)
}

export async function importCurrentCodexAccount(alias?: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-accounts/import-current`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alias }),
  }))
  return readJson<{ status: string; message?: string; accounts?: CodexAccountsStatus }>(res)
}

export async function refreshCodexAccountUsage(accountId?: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-accounts/refresh-usage`, withLocalHeader({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account_id: accountId }),
  }))
  return readJson<{ status: string; message?: string; accounts?: CodexAccountsStatus }>(res)
}

export async function switchCodexAccount(accountId: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-accounts/${accountId}/switch`, withLocalHeader({ method: 'POST' }))
  return readJson<{ status: string; message?: string; accounts?: CodexAccountsStatus }>(res)
}

export async function renameCodexAccount(accountId: string, alias: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-accounts/${accountId}`, withLocalHeader({
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ alias }),
  }))
  return readJson<{ status: string; message?: string; accounts?: CodexAccountsStatus }>(res)
}

export async function deleteCodexAccount(accountId: string) {
  const res = await fetchWithRetry(`${API_BASE}/codex-accounts/${accountId}`, withLocalHeader({ method: 'DELETE' }))
  return readJson<{ status: string; message?: string; accounts?: CodexAccountsStatus }>(res)
}
