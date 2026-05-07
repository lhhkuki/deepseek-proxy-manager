import { motion } from 'framer-motion'
import { Activity } from 'lucide-react'

interface HeaderProps {
  isRunning: boolean;
  autostart: boolean;
  onToggleAutostart: (enabled: boolean) => void;
  onToggleProxy: () => void;
}

export default function Header({ isRunning, autostart, onToggleAutostart, onToggleProxy }: HeaderProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="bg-white mx-4 mt-4 rounded-xl px-6 py-4 shadow-sm"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#4A90D9] flex items-center justify-center">
            <Activity className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-[#1d1d1f]">AI Proxy Manager</h1>
            <div className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${isRunning ? 'bg-[#34c759]' : 'bg-[#ff3b30]'} animate-pulse`} />
              <span className={`text-sm font-medium ${isRunning ? 'text-[#34c759]' : 'text-[#ff3b30]'}`}>
                {isRunning ? '运行中' : '已停止'}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onToggleProxy}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium text-white transition-colors ${
              isRunning
                ? 'bg-[#ff3b30] hover:bg-[#e0352b]'
                : 'bg-[#4A90D9] hover:bg-[#3a7bc8]'
            }`}
          >
            {isRunning ? '停止' : '启动'}
          </button>
          <label className="flex items-center gap-2 text-sm text-[#6e6e73] cursor-pointer">
            <input
              type="checkbox"
              checked={autostart}
              onChange={(e) => onToggleAutostart(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-[#4A90D9]"
            />
            开机启动
          </label>
        </div>
      </div>
    </motion.header>
  )
}