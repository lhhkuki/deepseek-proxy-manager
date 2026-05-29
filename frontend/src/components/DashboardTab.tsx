import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  CheckCircle,
  Download,
  FileClock,
  Gauge,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  UserRound,
  Wrench,
} from 'lucide-react'
import * as api from '../api'
import ConfirmDialog from './ConfirmDialog'
import type { BackupItem, BackupsStatus, DiagnosticStatus, LatestRelease } from '../types'

export default function DashboardTab() {
  const [diagnostics, setDiagnostics] = useState<DiagnosticStatus | null>(null)
  const [release, setRelease] = useState<LatestRelease | null>(null)
  const [backups, setBackups] = useState<BackupsStatus | null>(null)
  const [busy, setBusy] = useState<'refresh' | `restore:${string}` | null>(null)
  const [notice, setNotice] = useState('')
  const [backupToRestore, setBackupToRestore] = useState<BackupItem | null>(null)

  const failedChecks = useMemo(() => diagnostics?.checks.filter(check => !check.ok) || [], [diagnostics])
  const activeAccount = useMemo(() => diagnostics?.accounts.accounts.find(account => account.active), [diagnostics])
  const configBackups = useMemo(() => (backups?.items || []).filter(item => item.type === 'config'), [backups])

  const loadDashboard = async () => {
    const [diag, latest, backupList] = await Promise.all([
      api.getDiagnostics(),
      api.getLatestRelease(),
      api.getBackups(),
    ])
    setDiagnostics(diag)
    setRelease(latest)
    setBackups(backupList)
  }

  const refresh = async () => {
    setBusy('refresh')
    try {
      await loadDashboard()
      setNotice('')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  useEffect(() => {
    let cancelled = false
    Promise.all([
      api.getDiagnostics(),
      api.getLatestRelease(),
      api.getBackups(),
    ]).then(([diag, latest, backupList]) => {
      if (cancelled) return
      setDiagnostics(diag)
      setRelease(latest)
      setBackups(backupList)
    }).catch(e => {
      if (!cancelled) setNotice(e instanceof Error ? e.message : String(e))
    })
    return () => { cancelled = true }
  }, [])

  const restore = async (backup: BackupItem) => {
    setBusy(`restore:${backup.path}`)
    try {
      await api.restoreBackup(backup.path)
      setNotice(`已恢复 ${backup.type === 'config' ? '配置' : '账号'} 备份：${backup.name}`)
      setBackupToRestore(null)
      await loadDashboard()
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
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-[var(--text-muted)]" />
                <h2 className="text-[17px] font-semibold text-[var(--text-primary)]">运行总览</h2>
              </div>
              <p className="text-[12px] text-[var(--text-muted)] mt-1">代理、Codex、账号和配置的当前状态</p>
            </div>
            <button type="button" onClick={refresh} disabled={busy !== null}
              className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-50"
              aria-label="刷新总览">
              <RefreshCw className={`w-4 h-4 ${busy === 'refresh' ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            <StatusTile icon={<ShieldCheck className="w-4 h-4" />} label="代理" value={diagnostics?.status.running ? '运行中' : '已停止'} detail={`端口 ${diagnostics?.codex.base_url || diagnostics?.active_model.base_url || '-'}`} ok={diagnostics?.status.running} />
            <StatusTile icon={<Wrench className="w-4 h-4" />} label="Codex 模式" value={diagnostics?.codex.mode || '-'} detail={diagnostics?.codex.provider || diagnostics?.codex.config_path || '-'} ok={diagnostics?.codex.mode !== 'custom'} />
            <StatusTile icon={<Gauge className="w-4 h-4" />} label="当前模型" value={diagnostics?.active_model.id || '-'} detail={diagnostics?.active_model.base_url || '未配置'} ok={Boolean(diagnostics?.active_model.id)} />
            <StatusTile icon={<UserRound className="w-4 h-4" />} label="当前账号" value={activeAccount?.account || diagnostics?.accounts.current.account || '-'} detail={`${diagnostics?.accounts.accounts.length || 0} 个保存账号`} ok={Boolean(activeAccount || diagnostics?.accounts.current.exists)} />
          </div>
          {notice && <p className="text-[12px] text-[var(--text-muted)] mt-4 break-all">{notice}</p>}
        </motion.div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Panel title="诊断报告" icon={<CheckCircle className="w-5 h-5" />}>
            <div className="space-y-2">
              {(diagnostics?.checks || []).map(check => (
                <div key={check.key} className="flex items-start gap-3 rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-3">
                  {check.ok ? <CheckCircle className="w-4 h-4 text-success mt-0.5" /> : <AlertTriangle className="w-4 h-4 text-danger mt-0.5" />}
                  <div className="min-w-0">
                    <div className="text-[13px] font-semibold text-[var(--text-primary)]">{check.label}</div>
                    <div className="text-[12px] text-[var(--text-muted)] mt-1 break-all">{check.detail}</div>
                    {!check.ok && check.action && <div className="text-[12px] text-danger mt-1">{check.action}</div>}
                  </div>
                </div>
              ))}
              {failedChecks.length === 0 && diagnostics && (
                <p className="text-[12px] text-success">基础诊断未发现阻塞项。</p>
              )}
            </div>
          </Panel>

          <Panel title="更新检查" icon={<Download className="w-5 h-5" />}>
            <div className="rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-4">
              <div className="text-[14px] font-semibold text-[var(--text-primary)]">
                当前版本 {release?.current_version || diagnostics?.version || '-'}
              </div>
              <p className="text-[12px] text-[var(--text-muted)] mt-2">
                {release?.ok
                  ? release.update_available
                    ? `发现新版本 ${release.latest_version}`
                    : `已是最新版本 ${release.latest_version || release.current_version}`
                  : release?.message || '正在检查 GitHub Release'}
              </p>
              {release?.url && (
                <a href={release.url} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 mt-3 text-[13px] font-semibold text-accent hover:underline">
                  打开 Release 页面
                </a>
              )}
            </div>
            <div className="mt-3 rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-4">
              <div className="text-[13px] font-semibold text-[var(--text-primary)]">最近错误</div>
              <div className="mt-2 space-y-2">
                {(diagnostics?.recent_errors || []).length === 0 ? (
                  <p className="text-[12px] text-[var(--text-muted)]">暂无错误日志。</p>
                ) : diagnostics?.recent_errors.map(item => (
                  <div key={item.id} className="text-[12px] text-[var(--text-muted)] break-all">
                    {item.timestamp} · {item.message}
                  </div>
                ))}
              </div>
            </div>
          </Panel>
        </div>

        <Panel title="备份恢复" icon={<FileClock className="w-5 h-5" />}>
          <BackupGroup
            title="配置备份"
            description="只保留最近 20 个 config.toml 备份。账号登录态请在账号页管理。"
            items={configBackups}
            busy={busy}
            onRestore={setBackupToRestore}
          />
        </Panel>
        </div>
      </div>
      <ConfirmDialog
        open={Boolean(backupToRestore)}
        title="恢复配置备份"
        message={`确定恢复 ${backupToRestore?.name || ''} 吗？当前 config.toml 会先保留一份临时备份。`}
        confirmText="恢复"
        busy={Boolean(backupToRestore && busy === `restore:${backupToRestore.path}`)}
        onConfirm={() => backupToRestore && restore(backupToRestore)}
        onClose={() => setBackupToRestore(null)}
      />
    </>
  )
}

function BackupGroup({
  title,
  description,
  items,
  busy,
  onRestore,
}: {
  title: string;
  description: string;
  items: BackupItem[];
  busy: string | null;
  onRestore: (backup: BackupItem) => void;
}) {
  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-2 mb-2">
        <div>
          <h3 className="text-[14px] font-semibold text-[var(--text-primary)]">{title}</h3>
          <p className="text-[12px] text-[var(--text-muted)] mt-1">{description}</p>
        </div>
        <span className="text-[12px] text-[var(--text-muted)]">{items.length} 个备份</span>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {items.slice(0, 8).map(item => (
          <BackupCard key={item.path} item={item} busy={busy} onRestore={onRestore} />
        ))}
        {items.length === 0 && (
          <p className="text-[12px] text-[var(--text-muted)] rounded-[var(--radius-xs)] border border-dashed border-[var(--border)] bg-[var(--bg-primary)] p-4">
            暂无{title}。
          </p>
        )}
      </div>
    </section>
  )
}

function BackupCard({ item, busy, onRestore }: { item: BackupItem; busy: string | null; onRestore: (backup: BackupItem) => void }) {
  return (
    <div className="rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-[var(--text-primary)] truncate">{item.name}</div>
          <div className="text-[12px] text-[var(--text-muted)] mt-1">Codex 配置 · {item.updated_at}</div>
        </div>
        <button type="button" onClick={() => onRestore(item)} disabled={busy !== null}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-[var(--radius-xs)] border border-[var(--border)] text-[12px] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] disabled:opacity-50">
          <RotateCcw className="w-3.5 h-3.5" />
          恢复
        </button>
      </div>
      <div className="text-[11px] text-[var(--text-muted)] mt-2 truncate">{item.path}</div>
    </div>
  )
}

function Panel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="bg-surface rounded-[var(--radius-sm)] border border-[var(--border)] p-5">
      <div className="flex items-center gap-2 mb-4 text-[var(--text-muted)]">
        {icon}
        <h2 className="text-[16px] font-semibold text-[var(--text-primary)]">{title}</h2>
      </div>
      {children}
    </motion.div>
  )
}

function StatusTile({ icon, label, value, detail, ok }: { icon: ReactNode; label: string; value: string; detail: string; ok?: boolean }) {
  return (
    <div className="rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] p-3">
      <div className="flex items-center gap-2 text-[12px] text-[var(--text-muted)]">
        <span className={`inline-flex items-center justify-center w-7 h-7 rounded-md ${ok ? 'text-success bg-success-soft' : 'text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]'}`}>{icon}</span>
        {label}
      </div>
      <div className="text-[14px] font-semibold text-[var(--text-primary)] mt-2 truncate">{value}</div>
      <div className="text-[12px] text-[var(--text-muted)] mt-1 truncate">{detail}</div>
    </div>
  )
}
