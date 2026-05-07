import { motion } from 'framer-motion'
import { Terminal, Clock } from 'lucide-react'
import type { LogEntry } from '../types'

interface LogsTabProps {
  logs: LogEntry[];
}

export default function LogsTab({ logs }: LogsTabProps) {
  return (
    <div className="h-full flex flex-col px-4 pb-4">
      <div className="bg-white rounded-xl shadow-sm flex flex-col h-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#f0f0f2]">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-[#6e6e73]" />
            <span className="text-sm font-medium text-[#1d1d1f]">实时请求日志</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#34c759] animate-pulse" />
            <span className="text-xs text-[#6e6e73]">实时</span>
          </div>
        </div>

        {/* Logs List */}
        <div className="flex-1 overflow-y-auto p-2">
          {logs.length === 0 ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center h-full text-[#aeaeb2]"
            >
              <Terminal className="w-12 h-12 mb-3 opacity-30" />
              <p className="text-sm">暂无请求日志</p>
              <p className="text-xs mt-1">请求将在这里实时显示</p>
            </motion.div>
          ) : (
            <div className="space-y-1">
              {logs.map((log, idx) => (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.2, delay: Math.min(idx * 0.02, 0.3) }}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#f8f8f8] transition-colors"
                >
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Clock className="w-3.5 h-3.5 text-[#aeaeb2]" />
                    <span className="text-xs text-[#6e6e73] font-mono">{log.timestamp}</span>
                  </div>

                  <span className="text-sm text-[#1d1d1f] truncate flex-1">{log.message}</span>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
