import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, Save, CheckCircle } from 'lucide-react'

interface SettingsTabProps {
  port: number;
  onPortChange: (port: number) => void;
}

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
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="bg-white rounded-xl shadow-sm p-6"
      >
        <div className="flex items-center gap-2 mb-6">
          <Settings className="w-5 h-5 text-[#6e6e73]" />
          <h2 className="text-lg font-bold text-[#1d1d1f]">代理设置</h2>
        </div>

        <div className="space-y-5">
          <div>
            <label className="block text-sm text-[#6e6e73] mb-2">代理端口</label>
            <input
              type="number"
              value={localPort}
              onChange={(e) => setLocalPort(e.target.value)}
              min={1}
              max={65535}
              className="w-48 px-4 py-2.5 bg-[#f8f8f8] border border-[#e5e5e8] rounded-lg text-[#1d1d1f] text-sm focus:outline-none focus:ring-2 focus:ring-[#4A90D9]/30 focus:border-[#4A90D9] transition-all"
            />
            <p className="text-xs text-[#aeaeb2] mt-1.5">修改端口后需要重启代理才能生效</p>
          </div>

          <div className="flex items-center gap-3 pt-4 border-t border-[#f0f0f2]">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSave}
              className="flex items-center gap-2 px-5 py-2.5 bg-[#4A90D9] text-white text-sm font-medium rounded-lg hover:bg-[#3a7bc8] transition-colors shadow-sm"
            >
              <Save className="w-4 h-4" />
              保存设置
            </motion.button>

            <AnimatePresence>
              {saved && (
                <motion.div
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  className="flex items-center gap-1.5 text-sm text-[#34c759]"
                >
                  <CheckCircle className="w-4 h-4" />
                  已保存
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
