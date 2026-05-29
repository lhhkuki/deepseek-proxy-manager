import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { CalendarDays, CheckCircle, Clock3, Gauge, KeyRound, RefreshCw, ShieldCheck, Trash2, UserRound, WalletCards } from 'lucide-react'
import * as api from '../api'
import ConfirmDialog from './ConfirmDialog'
import type { CodexAccount, CodexAccountsStatus, CodexQuotaWindow } from '../types'

type BusyState =
  | 'refresh'
  | 'usage:all'
  | 'import'
  | `usage:${string}`
  | `switch:${string}`
  | `delete:${string}`
  | null

function accountName(account?: CodexAccount | null) {
  if (!account) return ''
  return account.account || account.alias || account.id
}

export default function AccountsTab() {
  const [status, setStatus] = useState<CodexAccountsStatus | null>(null)
  const [busy, setBusy] = useState<BusyState>(null)
  const [notice, setNotice] = useState('')
  const [accountToDelete, setAccountToDelete] = useState<CodexAccount | null>(null)

  const activeAccount = useMemo(() => status?.accounts.find(account => account.active) || null, [status])

  const refresh = async () => {
    setBusy('refresh')
    try {
      setStatus(await api.getCodexAccounts())
      setNotice('')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  useEffect(() => {
    let cancelled = false
    api.getCodexAccounts()
      .then(result => {
        if (!cancelled) setStatus(result)
      })
      .catch(e => {
        if (!cancelled) setNotice(e instanceof Error ? e.message : String(e))
      })
    return () => { cancelled = true }
  }, [])

  const applyResult = (result: { status: string; message?: string; accounts?: CodexAccountsStatus }, fallback: string) => {
    if (result.status !== 'ok' || !result.accounts) {
      throw new Error(result.message || fallback)
    }
    setStatus(result.accounts)
    return result.accounts
  }

  const importCurrent = async () => {
    setBusy('import')
    try {
      const next = applyResult(await api.importCurrentCodexAccount(), '导入当前账号失败')
      const current = next.accounts.find(account => account.active)
      setNotice(current ? `已保存当前账号：${accountName(current)}` : `已保存当前账号，共 ${next.accounts.length} 个账号`)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const refreshUsage = async (account?: CodexAccount) => {
    setBusy(account ? `usage:${account.id}` : 'usage:all')
    try {
      const next = applyResult(await api.refreshCodexAccountUsage(account?.id), '刷新额度失败')
      setNotice(account ? `已刷新 ${accountName(account)} 的额度` : `已刷新 ${next.accounts.length} 个账号额度`)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const switchAccount = async (account: CodexAccount) => {
    setBusy(`switch:${account.id}`)
    try {
      const next = applyResult(await api.switchCodexAccount(account.id), '切换账号失败')
      setNotice(next.backup_path ? `已切换账号，原 auth 已备份：${next.backup_path}` : `已切换账号：${accountName(account)}`)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const deleteAccount = async (account: CodexAccount) => {
    setBusy(`delete:${account.id}`)
    try {
      applyResult(await api.deleteCodexAccount(account.id), '删除账号失败')
      setNotice('已删除账号副本')
      setAccountToDelete(null)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="h-full overflow-y-auto px-4 pb-4">
        <div className="space-y-4">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="bg-surface rounded-[var(--radius-sm)] border border-[var(--border)] p-6">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div className="flex items-center gap-2">
              <WalletCards className="w-5 h-5 text-[var(--text-muted)]" />
              <h2 className="text-[17px] font-semibold text-[var(--text-primary)]">Codex 账号管理</h2>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => refreshUsage()} disabled={busy !== null || !status?.accounts.length}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-50">
                <Gauge className={`w-4 h-4 ${busy === 'usage:all' ? 'animate-pulse' : ''}`} />
                刷新额度
              </button>
              <button type="button" onClick={refresh} disabled={busy !== null}
                className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-50">
                <RefreshCw className={`w-4 h-4 ${busy === 'refresh' ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-5">
            <StatusTile icon={<UserRound className="w-4 h-4" />} label="当前 auth" value={status?.current.exists ? (status.current.account || '已检测') : '未检测到'}
              detail={status?.current.auth_mode || status?.auth_path || '正在读取 Codex auth.json'} tone={status?.current.exists ? 'text-success bg-success-soft' : 'text-danger bg-danger-soft'} />
            <StatusTile icon={<WalletCards className="w-4 h-4" />} label="保存账号" value={`${status?.accounts.length || 0} 个`}
              detail={activeAccount ? `当前：${accountName(activeAccount)}` : '尚未匹配到已保存账号'} tone="text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]" />
            <StatusTile icon={<ShieldCheck className="w-4 h-4" />} label="存储位置" value="本地保险箱"
              detail={status?.vault_path || '读取中'} tone="text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]" />
          </div>

          <button type="button" onClick={importCurrent} disabled={busy !== null || !status?.current.exists}
            className="px-5 py-2.5 bg-accent text-white text-[13px] font-semibold rounded-[var(--radius-xs)] hover:bg-blue-700 transition-colors duration-200 shadow-sm disabled:opacity-60">
            保存当前 Codex 账号
          </button>
          {notice && <p className="text-[12px] text-[var(--text-muted)] mt-4 break-all">{notice}</p>}
        </motion.div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {(status?.accounts || []).map((account, index) => (
            <motion.div key={account.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, delay: index * 0.03, ease: [0.22, 1, 0.36, 1] }}
              className={`bg-surface rounded-[var(--radius-sm)] border p-5 ${account.active ? 'border-accent shadow-sm' : 'border-[var(--border)]'}`}>
              <div className="flex items-start justify-between gap-3 mb-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="text-[15px] font-semibold text-[var(--text-primary)] truncate">{accountName(account)}</h3>
                    {account.active && <span className="inline-flex items-center gap-1 text-[12px] text-success"><CheckCircle className="w-3.5 h-3.5" />当前</span>}
                  </div>
                  <p className="text-[12px] text-[var(--text-muted)] mt-1 truncate">{account.auth_mode || account.id}</p>
                </div>
                <div className="flex items-center gap-1">
                  <button type="button" onClick={() => refreshUsage(account)} disabled={busy !== null}
                    className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-accent hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-50"
                    title="刷新额度">
                    <Gauge className={`w-4 h-4 ${busy === `usage:${account.id}` ? 'animate-pulse' : ''}`} />
                  </button>
                  <button type="button" onClick={() => setAccountToDelete(account)} disabled={busy !== null}
                    className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-danger hover:bg-danger-soft transition-colors disabled:opacity-50">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <UsagePanel account={account} />

              <div className="grid grid-cols-2 gap-3 mb-4">
                <MiniStat label="类型" value={account.has_chatgpt_token ? 'ChatGPT' : account.has_api_key ? 'API Key' : account.auth_mode || '未知'} icon={<KeyRound className="w-3.5 h-3.5" />} />
                <MiniStat label="保存时间" value={account.updated_at || account.created_at || '-'} icon={<RefreshCw className="w-3.5 h-3.5" />} />
              </div>

              <button type="button" onClick={() => switchAccount(account)} disabled={busy !== null || account.active}
                className="w-full px-4 py-2 bg-accent text-white text-[13px] font-semibold rounded-[var(--radius-xs)] hover:bg-blue-700 disabled:opacity-60">
                切换
              </button>
            </motion.div>
          ))}
        </div>
        </div>
      </div>
      <ConfirmDialog
        open={Boolean(accountToDelete)}
        title="删除账号"
        message={`确定删除账号「${accountName(accountToDelete)}」吗？这只会删除本工具保存的账号副本，不会退出 Codex 当前登录。`}
        confirmText="删除"
        danger
        busy={Boolean(accountToDelete && busy === `delete:${accountToDelete.id}`)}
        onConfirm={() => accountToDelete && deleteAccount(accountToDelete)}
        onClose={() => setAccountToDelete(null)}
      />
    </>
  )
}

function UsagePanel({ account }: { account: CodexAccount }) {
  const usage = account.usage
  const message = usage && !usage.ok ? usage.message : usage?.updated_at ? `额度刷新于 ${usage.updated_at}` : '点击仪表盘按钮刷新'

  return (
    <div className="rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-3 mb-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--text-muted)]">
          <Gauge className="w-3.5 h-3.5" />
          账号额度
        </div>
        {usage?.plan_type && <span className="text-[11px] text-[var(--text-muted)]">{usage.plan_type}</span>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <QuotaStat label="五小时额度" window={usage?.primary} icon={<Clock3 className="w-3.5 h-3.5" />} />
        <QuotaStat label="周额度" window={usage?.secondary} icon={<CalendarDays className="w-3.5 h-3.5" />} />
      </div>
      <div className={`text-[11px] mt-3 truncate ${usage && !usage.ok ? 'text-danger' : 'text-[var(--text-muted)]'}`}>{message}</div>
    </div>
  )
}

function formatResetTime(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '刷新时间 -'
  const raw = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(raw)) return '刷新时间 -'
  const millis = raw > 10_000_000_000 ? raw : raw * 1000
  const date = new Date(millis)
  if (Number.isNaN(date.getTime())) return '刷新时间 -'
  return `刷新 ${date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })}`
}

function QuotaStat({ icon, label, window }: { icon: ReactNode; label: string; window?: CodexQuotaWindow | null }) {
  const used = typeof window?.used_percent === 'number' ? window.used_percent : null
  const remaining = typeof window?.remaining_percent === 'number' ? window.remaining_percent : null
  const value = remaining === null ? '未刷新' : `剩余 ${Math.round(remaining)}%`
  const detail = used === null ? '等待读取' : `已用 ${Math.round(used)}%`
  const resetText = formatResetTime(window?.resets_at)
  const bar = used === null ? 0 : Math.max(0, Math.min(100, used))

  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 text-[12px] text-[var(--text-muted)]">{icon}{label}</div>
      <div className="flex items-baseline justify-between gap-2 mt-1">
        <span className="text-[13px] font-semibold text-[var(--text-primary)] truncate">{value}</span>
        <span className="text-[11px] text-[var(--text-muted)] shrink-0">{detail}</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--bg-surface-hover)] mt-2 overflow-hidden">
        <div className="h-full rounded-full bg-accent transition-all duration-300" style={{ width: `${bar}%` }} />
      </div>
      <div className="text-[11px] text-[var(--text-muted)] mt-1 truncate">{resetText}</div>
    </div>
  )
}

function StatusTile({ icon, label, value, detail, tone }: { icon: ReactNode; label: string; value: string; detail: string; tone: string }) {
  return (
    <div className="rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-3">
      <div className="flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
        <span className={`inline-flex items-center justify-center w-7 h-7 rounded-md ${tone}`}>{icon}</span>
        {label}
      </div>
      <div className="text-[14px] font-semibold text-[var(--text-primary)] mt-2 truncate">{value}</div>
      <div className="text-[12px] text-[var(--text-muted)] mt-1 leading-5 truncate">{detail}</div>
    </div>
  )
}

function MiniStat({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xs)] bg-[var(--bg-primary)] border border-[var(--border)] px-3 py-2">
      <div className="flex items-center gap-1.5 text-[12px] text-[var(--text-muted)]">{icon}{label}</div>
      <div className="text-[13px] font-medium text-[var(--text-primary)] mt-1 truncate">{value}</div>
    </div>
  )
}
