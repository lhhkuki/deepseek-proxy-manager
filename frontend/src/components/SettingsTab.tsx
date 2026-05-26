import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, KeyRound, RefreshCw, Save, Settings, ShieldCheck, Shuffle, UserRound } from 'lucide-react'
import * as api from '../api'
import type { CodexConfigStatus } from '../types'

interface SettingsTabProps {
  port: number;
  activeModelId?: string;
  onPortChange: (port: number) => void;
}

const modeCopy = {
  official: { label: '官方账号', tone: 'text-success bg-success-soft', detail: 'Codex 将使用 ChatGPT 官方登录态' },
  proxy: { label: '第三方插件兼容', tone: 'text-accent bg-accent-soft', detail: '插件保留官方登录，模型请求走本地代理' },
  custom: { label: '其他配置', tone: 'text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]', detail: '当前 config.toml 使用了其他 provider' },
}

export default function SettingsTab({ port, activeModelId, onPortChange }: SettingsTabProps) {
  const [localPort, setLocalPort] = useState(port.toString())
  const [saved, setSaved] = useState(false)
  const [codex, setCodex] = useState<CodexConfigStatus | null>(null)
  const [busy, setBusy] = useState<'official' | 'proxy' | 'refresh' | null>(null)
  const [notice, setNotice] = useState('')

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
    return () => { cancelled = true }
  }, [])

  const handleSave = () => {
    const p = parseInt(localPort)
    if (p >= 1 && p <= 65535) {
      onPortChange(p)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } else {
      alert('端口必须是 1-65535 的整数')
    }
  }

  const applyMode = async (mode: 'official' | 'proxy') => {
    setBusy(mode)
    setNotice('')
    try {
      const result = mode === 'official'
        ? await api.applyOfficialCodexConfig()
        : await api.applyProxyCodexConfig(parseInt(localPort) || port, activeModelId)
      if (result.status !== 'ok' || !result.codex) {
        throw new Error(result.message || '切换失败')
      }
      setCodex(result.codex)
      setNotice(result.codex.backup_path ? `已备份：${result.codex.backup_path}` : '已写入 Codex 配置')
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
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
                className="w-52 px-4 py-2.5 bg-[var(--bg-primary)] border border-[var(--border)] rounded-[var(--radius-xs)] text-[var(--text-primary)] text-[14px] outline-none transition-all duration-200 focus:border-accent focus:ring-1 focus:ring-accent/20 focus:bg-surface hover:border-[var(--border-hover)]"
              />
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
            <StatusTile icon={<UserRound className="w-4 h-4" />} label="官方登录" value={codex?.auth.authenticated ? '已登录' : '未检测到'} detail={codex?.auth.message || '正在读取 auth.json'} tone={codex?.auth.authenticated ? 'text-success bg-success-soft' : 'text-danger bg-danger-soft'} />
            <StatusTile icon={<KeyRound className="w-4 h-4" />} label="当前模型" value={activeModelId || codex?.model || '未选择'} detail={codex?.provider ? `provider: ${codex.provider}` : '将使用启用中的模型'} tone="text-[var(--text-secondary)] bg-[var(--bg-surface-hover)]" />
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => applyMode('official')} disabled={busy !== null}
              className={modeButtonClass(codex?.mode === 'official')}>
              <span className="block text-[14px] font-semibold">切回官方账号</span>
              <span className={modeDetailClass(codex?.mode === 'official')}>移除 AIProxyManager provider，不改 auth.json</span>
            </motion.button>
            <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }} onClick={() => applyMode('proxy')} disabled={busy !== null}
              className={modeButtonClass(codex?.mode === 'proxy')}>
              <span className="block text-[14px] font-semibold">启用第三方插件兼容</span>
              <span className={modeDetailClass(codex?.mode === 'proxy')}>保留官方登录态，模型请求走本地代理</span>
            </motion.button>
          </div>

          {notice && <p className="text-[12px] text-[var(--text-muted)] mt-4 break-all">{notice}</p>}
          <p className="text-[12px] text-[var(--text-muted)] mt-3 break-all">配置文件：{codex?.config_path || '读取中'}</p>
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
