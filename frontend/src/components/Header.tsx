import { motion } from 'framer-motion'
import { Activity, Power } from 'lucide-react'

interface HeaderProps {
  isRunning: boolean;
  autostart: boolean;
  onToggleAutostart: (enabled: boolean) => void;
  onToggleProxy: () => void;
}

export default function Header({ isRunning, autostart, onToggleAutostart, onToggleProxy }: HeaderProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className="bg-surface mx-4 mt-4 rounded-xl px-6 py-4 border border-[var(--border)]"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-[var(--radius-sm)] bg-accent flex items-center justify-center shadow-sm">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-[17px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">AI Proxy Manager</h1>
            <div className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-success' : 'bg-danger'}`} />
              <span className={`text-[13px] font-medium ${isRunning ? 'text-success' : 'text-danger'}`}>
                {isRunning ? '运行中' : '已停止'}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={onToggleProxy}
            className={`group flex items-center gap-1.5 px-4 py-2 rounded-[var(--radius-xs)] text-[13px] font-semibold transition-all duration-200 ${
              isRunning ? 'bg-danger-soft text-danger hover:bg-danger hover:text-white' : 'bg-accent-soft text-accent hover:bg-accent hover:text-white'
            }`}>
            <Power className="w-3.5 h-3.5 transition-transform duration-200 group-active:scale-90" />
            {isRunning ? '停止' : '启动'}
          </button>
          <label className="flex items-center gap-2 text-[13px] text-[var(--text-secondary)] cursor-pointer select-none">
            <input type="checkbox" checked={autostart} onChange={(e)=>onToggleAutostart(e.target.checked)}
              className="w-4 h-4 rounded-[4px] border-[var(--border)] accent-accent cursor-pointer" />
            开机启动
          </label>
        </div>
      </div>
    </motion.header>
  )
}
