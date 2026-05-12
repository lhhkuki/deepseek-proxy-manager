import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, Save, CheckCircle } from 'lucide-react'

interface SettingsTabProps { port: number; onPortChange: (port: number) => void; }

export default function SettingsTab({ port, onPortChange }: SettingsTabProps) {
  const [localPort, setLocalPort] = useState(port.toString())
  const [saved, setSaved] = useState(false)

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

  return (
    <div className="h-full flex flex-col px-4 pb-4">
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
    </div>
  )
}
