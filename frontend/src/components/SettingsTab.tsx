import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, KeyRound, PlugZap, RefreshCw, Rocket, Save, Settings, ShieldCheck, Shuffle, UserRound } from 'lucide-react'
import * as api from '../api'
import type { CodexConfigStatus, CodexLauncherStatus } from '../types'

interface SettingsTabProps {
  port: number;
  activeModelId?: string;
  onPortChange: (port: number) => void;
}

const modeCopy = {
  official: { label: '官方账号', tone: 'text-success bg-success-soft', detail: 'Codex 将使用 ChatGPT 官方登录态' },
  proxy: { label: '第三方插件兼容', tone: 'text-accent bg-accent-soft', detail: '插件保留官方登录，模型请求走本地代理' },
  pure_api: { label: '纯 API', tone: 'text-accent bg-accent-soft', detail: '不依赖官方登录，配合启动器注入插件入口' },
  custom: { label: '其他配置', tone: 'text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]', detail: '当前 config.toml 使用了其他 provider' },
}

export default function SettingsTab({ port, activeModelId, onPortChange }: SettingsTabProps) {
  const [localPort, setLocalPort] = useState(port.toString())
  const [saved, setSaved] = useState(false)
  const [codex, setCodex] = useState<CodexConfigStatus | null>(null)
  const [launcher, setLauncher] = useState<CodexLauncherStatus | null>(null)
  const [busy, setBusy] = useState<'official' | 'proxy' | 'pure_api' | 'refresh' | 'launch' | 'relaunch' | 'inject' | 'stop' | null>(null)
  const [notice, setNotice] = useState('')
  const [launcherNotice, setLauncherNotice] = useState('')
  const [portError, setPortError] = useState('')

  const currentMode = useMemo(() => modeCopy[codex?.mode || 'official'], [codex])
  const modeButtonClass = (active: boolean) =>
    `flex-1 px-4 py-3 rounded-[var(--radius-xs)] border transition-colors disabled:opacity-60 ${
      active
        ? 'border-accent bg-accent text-white hover:bg-blue-700 shadow-sm'
        : 'border-[var(--border)] bg-[var(--bg-primary)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)]'
    }`
  const modeDetailClass = (active: boolean) =>
    `block text-[12px] mt-1 ${active ? 'text-white/75' : 'text-[var(--text-muted)]'}`

  const refreshCodex = async () => {
    setBusy('refresh')
    try {
      setCodex(await api.getCodexConfigStatus())
      setLauncher(await api.getCodexLauncherStatus())
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  useEffect(() => {
    let cancelled = false
    api.getCodexConfigStatus()
      .then(status => {
        if (!cancelled) setCodex(status)
      })
      .catch(e => {
        if (!cancelled) setNotice(e instanceof Error ? e.message : String(e))
      })
    api.getCodexLauncherStatus()
      .then(status => {
        if (!cancelled) setLauncher(status)
      })
      .catch(e => {
        if (!cancelled) setLauncherNotice(e instanceof Error ? e.message : String(e))
      })
    return () => { cancelled = true }
  }, [])

  const handleSave = () => {
    const p = parseInt(localPort)
    if (p >= 1 && p <= 65535) {
      setPortError('')
      onPortChange(p)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } else {
      setPortError('端口必须是 1-65535 的整数')
    }
  }

  const applyMode = async (mode: 'official' | 'proxy' | 'pure_api') => {
    setBusy(mode)
    setNotice('')
    try {
      const result = mode === 'official'
        ? await api.applyOfficialCodexConfig()
        : mode === 'pure_api'
          ? await api.applyPureApiCodexConfig(parseInt(localPort) || port, activeModelId)
          : await api.applyProxyCodexConfig(parseInt(localPort) || port, activeModelId)
      if (result.status !== 'ok' || !result.codex) {
        throw new Error(result.message || '切换失败')
      }
      setCodex(result.codex)
      const sync = result.codex.conversation_sync
      const syncText = sync
        ? `；会话同步 ${sync.changed_session_files} 个文件 / ${sync.sqlite_rows_updated} 条索引`
        : ''
      setNotice((result.codex.backup_path ? `已备份：${result.codex.backup_path}` : '已写入 Codex 配置') + syncText)
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  const runLauncherAction = async (action: 'launch' | 'relaunch' | 'inject' | 'stop') => {
    setBusy(action)
    setLauncherNotice('')
    try {
      const result = action === 'inject'
        ? await api.injectCodexUnlocks()
        : action === 'stop'
          ? await api.stopCodexProcesses()
          : await api.launchCodexWithUnlocks(action === 'relaunch')
      if (result.status !== 'ok' || !result.launcher) {
        throw new Error(result.message || 'Codex 启动器操作失败')
      }
      setLauncher(result.launcher)
      setLauncherNotice(action === 'stop' ? '已关闭现有 Codex 进程' : (result.launcher.last_inject.message || 'Codex 插件增强已注入'))
    } catch (e) {
      setLauncherNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="h-full overflow-y-auto px-4 pb-4">
      <div className="space-y-4">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="bg-surface rounded-[var(--radius-sm)] border border-[var(--border)] p-6">
          <div className="flex items-center gap-2 mb-6">
            <Settings className="w-5 h-5 text-[var(--text-muted)]" />
            <h2 className="text-[17px] font-semibold text-[var(--text-primary)]">代理设置</h2>
          </div>
          <div className="space-y-5">
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-secondary)] mb-2">代理端口</label>
              <input type="number" value={localPort} onChange={(e)=>setLocalPort(e.target.value)} min={1} max={65535}
                className={`w-52 px-4 py-2.5 bg-[var(--bg-primary)] border rounded-[var(--radius-xs)] text-[var(--text-primary)] text-[14px] outline-none transition-all duration-200 focus:ring-1 focus:bg-surface ${
                  portError
                    ? 'border-danger focus:border-danger focus:ring-danger/20'
                    : 'border-[var(--border)] hover:border-[var(--border-hover)] focus:border-accent focus:ring-accent/20'
                }`}
              />
              {portError && <p className="text-[12px] text-danger mt-1.5">{portError}</p>}
              <p className="text-[12px] text-[var(--text-muted)] mt-1.5">修改端口后需要重启代理才能生效</p>
            </div>
            <div className="flex items-center gap-3 pt-4 border-t border-[var(--border)]">
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={handleSave}
                className="flex items-center gap-2 px-5 py-2.5 bg-accent text-white text-[13px] font-semibold rounded-[var(--radius-xs)] hover:bg-blue-700 transition-colors duration-200 shadow-sm">
                <Save className="w-4 h-4" />保存设置
              </motion.button>
              <AnimatePresence>
                {saved && (
                  <motion.div initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -6 }} transition={{ duration: 0.2 }}
                    className="flex items-center gap-1.5 text-[13px] text-success font-medium">
                    <CheckCircle className="w-4 h-4" />已保存
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.04, ease: [0.22, 1, 0.36, 1] }}
          className="bg-surface rounded-[var(--radius-sm)] border border-[var(--border)] p-6">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div className="flex items-center gap-2">
              <Shuffle className="w-5 h-5 text-[var(--text-muted)]" />
              <h2 className="text-[17px] font-semibold text-[var(--text-primary)]">Codex 配置切换</h2>
            </div>
            <button type="button" onClick={refreshCodex} disabled={busy !== null}
              className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-50">
              <RefreshCw className={`w-4 h-4 ${busy === 'refresh' ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-5">
            <StatusTile icon={<ShieldCheck className="w-4 h-4" />} label="当前模式" value={currentMode.label} detail={currentMode.detail} tone={currentMode.tone} />
            <StatusTile icon={<UserRound className="w-4 h-4" />} label="官方登录" value={codex?.auth.authenticated ? '已登录' : '未检测到'} detail={codex?.auth.message || codex?.api_auth.message || '正在读取 auth.json'} tone={codex?.auth.authenticated || codex?.api_auth.authenticated ? 'text-success bg-success-soft' : 'text-danger bg-danger-soft'} />
            <StatusTile icon={<KeyRound className="w-4 h-4" />} label="当前模型" value={activeModelId || codex?.model || '未选择'} detail={codex?.provider ? `provider: ${codex.provider}` : '将使用启用中的模型'} tone="text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => applyMode('official')} disabled={busy !== null}
              className={modeButtonClass(codex?.mode === 'official')}>
              <span className="block text-[14px] font-semibold">切回官方账号</span>
              <span className={modeDetailClass(codex?.mode === 'official')}>移除 AIProxyManager 和纯 API Key</span>
            </motion.button>
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => applyMode('proxy')} disabled={busy !== null}
              className={modeButtonClass(codex?.mode === 'proxy')}>
              <span className="block text-[14px] font-semibold">启用第三方插件兼容</span>
              <span className={modeDetailClass(codex?.mode === 'proxy')}>保留官方登录态，模型请求走本地代理</span>
            </motion.button>
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => applyMode('pure_api')} disabled={busy !== null}
              className={modeButtonClass(codex?.mode === 'pure_api')}>
              <span className="block text-[14px] font-semibold">启用纯 API</span>
              <span className={modeDetailClass(codex?.mode === 'pure_api')}>无需官方登录，需用下方启动器打开 Codex</span>
            </motion.button>
          </div>

          {notice && <p className="text-[12px] text-[var(--text-muted)] mt-4 break-all">{notice}</p>}
          <p className="text-[12px] text-[var(--text-muted)] mt-3 break-all">配置文件：{codex?.config_path || '读取中'}</p>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
          className="bg-surface rounded-[var(--radius-sm)] border border-[var(--border)] p-6">
          <div className="flex items-start justify-between gap-4 mb-5">
            <div className="flex items-center gap-2">
              <Rocket className="w-5 h-5 text-[var(--text-muted)]" />
              <h2 className="text-[17px] font-semibold text-[var(--text-primary)]">Codex 启动器</h2>
            </div>
            <button type="button" onClick={refreshCodex} disabled={busy !== null}
              className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-50">
              <RefreshCw className={`w-4 h-4 ${busy === 'refresh' ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-5">
            <StatusTile icon={<PlugZap className="w-4 h-4" />} label="调试连接" value={launcher?.cdp_available ? '已连接' : '未连接'} detail={`端口：${launcher?.debug_port || 9231}`} tone={launcher?.cdp_available ? 'text-success bg-success-soft' : 'text-danger bg-danger-soft'} />
            <StatusTile icon={<Rocket className="w-4 h-4" />} label="Codex 进程" value={`${launcher?.processes?.length || 0} 个`} detail={launcher?.codex_exe ? '已找到 Codex 程序' : '未找到 Codex 程序'} tone={launcher?.codex_exe ? 'text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]' : 'text-danger bg-danger-soft'} />
            <StatusTile icon={<ShieldCheck className="w-4 h-4" />} label="插件增强" value={launcher?.last_inject.ok ? '已注入' : '未注入'} detail={launcher?.last_inject.updated_at || launcher?.last_inject.message || '等待启动器注入'} tone={launcher?.last_inject.ok ? 'text-success bg-success-soft' : 'text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]'} />
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => runLauncherAction('relaunch')} disabled={busy !== null}
              className="flex-1 px-4 py-3 rounded-[var(--radius-xs)] bg-accent text-white hover:bg-blue-700 transition-colors shadow-sm disabled:opacity-60">
              <span className="block text-[14px] font-semibold">启动增强版 Codex</span>
              <span className="block text-[12px] text-white/75 mt-1">使用独立 profile，避免被已有 Codex 占用</span>
            </motion.button>
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => runLauncherAction('inject')} disabled={busy !== null || !launcher?.cdp_available}
              className="flex-1 px-4 py-3 rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-60">
              <span className="block text-[14px] font-semibold">重新注入增强</span>
              <span className="block text-[12px] text-[var(--text-muted)] mt-1">Codex 已通过启动器打开时使用</span>
            </motion.button>
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => runLauncherAction('stop')} disabled={busy !== null || !launcher?.processes?.length}
              className="flex-1 px-4 py-3 rounded-[var(--radius-xs)] border border-[var(--border)] bg-[var(--bg-primary)] text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors disabled:opacity-60">
              <span className="block text-[14px] font-semibold">关闭增强版 Codex</span>
              <span className="block text-[12px] text-[var(--text-muted)] mt-1">只关闭由启动器打开的 Codex</span>
            </motion.button>
          </div>

          {launcherNotice && <p className="text-[12px] text-[var(--text-muted)] mt-4 break-all">{launcherNotice}</p>}
          <p className="text-[12px] text-[var(--text-muted)] mt-3 break-all">Codex 程序：{launcher?.codex_exe || '未检测到'}</p>
        </motion.div>
      </div>
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
      <div className="text-[12px] text-[var(--text-muted)] mt-1 leading-5">{detail}</div>
    </div>
  )
}
