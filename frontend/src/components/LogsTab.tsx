import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Terminal, AlertTriangle, XCircle, Info, Search, X } from 'lucide-react'
import type { LogEntry } from '../types'

interface LogsTabProps { logs: LogEntry[] }

const levelConfig = {
  info: { icon: Info, color: 'text-accent', bg: 'bg-accent-soft' },
  warn: { icon: AlertTriangle, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  error: { icon: XCircle, color: 'text-danger', bg: 'bg-danger-soft' },
}

export default function LogsTab({ logs }: LogsTabProps) {
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search.trim()) return logs
    const q = search.toLowerCase()
    return logs.filter(log => log.message.toLowerCase().includes(q))
  }, [logs, search])

  return (
    <div className="h-full flex flex-col px-4 pb-4">
      <div className="bg-surface rounded-[var(--radius-sm)] border border-[var(--border)] flex flex-col h-full overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-[var(--text-muted)]" />
            <span className="text-[13px] font-semibold text-[var(--text-primary)]">实时请求日志</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-success" />
            <span className="text-[11px] font-medium text-[var(--text-muted)]">实时</span>
          </div>
        </div>

        {/* ── Search bar ── */}
        <div className="px-3 py-2 border-b border-[var(--border)]">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-muted)]" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="搜索日志..."
              className="w-full pl-7 pr-8 py-1.5 text-[12px] rounded-[var(--radius-xs)] 
                         bg-[var(--bg-surface-hover)] border border-[var(--border)]
                         text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
                         focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/20
                         transition-colors duration-150"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] 
                           hover:text-[var(--text-primary)] transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
          {/* ── Filter stats ── */}
          {search.trim() && (
            <div className="mt-1.5 text-[11px] text-[var(--text-muted)]">
              显示 {filtered.length} / {logs.length} 条
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}
              className="flex flex-col items-center justify-center h-full text-[var(--text-muted)]">
              <div className="w-16 h-16 rounded-full bg-[var(--bg-surface-hover)] flex items-center justify-center mb-4">
                <Terminal className="w-8 h-8 opacity-40" />
              </div>
              {logs.length === 0 ? (
                <>
                  <p className="text-[15px] font-medium text-[var(--text-secondary)]">暂无请求日志</p>
                  <p className="text-[13px] mt-1">请求将在这里实时显示</p>
                </>
              ) : (
                <>
                  <p className="text-[15px] font-medium text-[var(--text-secondary)]">无匹配结果</p>
                  <p className="text-[13px] mt-1">尝试其他关键词</p>
                </>
              )}
            </motion.div>
          ) : (
            <div className="space-y-0.5">
              {filtered.map((log) => {
                const cfg = levelConfig[log.level || 'info'] || levelConfig.info
                const Icon = cfg.icon
                return (
                  <div key={log.id} className="flex items-start gap-2.5 px-3 py-2 rounded-[var(--radius-xs)] hover:bg-[var(--bg-surface-hover)] transition-colors duration-150 group">
                    <div className={`shrink-0 mt-0.5 w-5 h-5 rounded-[4px] ${cfg.bg} ${cfg.color} flex items-center justify-center`}><Icon className="w-3 h-3" /></div>
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[11px] font-mono text-[var(--text-muted)] shrink-0">{log.timestamp}</span>
                      <span className="text-[13px] text-[var(--text-primary)] truncate">{log.message}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
