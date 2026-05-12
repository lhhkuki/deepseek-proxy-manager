import { motion, AnimatePresence } from 'framer-motion'
import { Plus, ServerOff } from 'lucide-react'
import ModelCard from './ModelCard'
import type { Model } from '../types'

interface ModelsTabProps {
  models: Model[];
  loading?: boolean;
  onToggle: (idx: number) => void;
  onDelete: (idx: number) => void;
  onEdit: (model: Model) => void;
  onAdd: () => void;
}

export default function ModelsTab({ models, loading, onToggle, onDelete, onEdit, onAdd }: ModelsTabProps) {
  return (
    <div className="h-full flex flex-col px-4 pb-4">
      <div className="mb-3">
        <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={onAdd}
          className="flex items-center gap-2 px-4 py-2.5 bg-accent text-white text-[13px] font-semibold rounded-[var(--radius-sm)] hover:bg-blue-700 transition-colors duration-200 shadow-sm">
          <Plus className="w-4 h-4" />添加模型
        </motion.button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="space-y-3 pr-2">
            {[0,1,2].map(i=><div key={i} className="h-[76px] rounded-[var(--radius-sm)] bg-surface border border-[var(--border)] animate-pulse"/>)}
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            {models.length === 0 ? (
              <motion.div key="empty" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                className="flex flex-col items-center justify-center h-full text-[var(--text-muted)]">
                <div className="w-16 h-16 rounded-full bg-[var(--bg-surface-hover)] flex items-center justify-center mb-4"><ServerOff className="w-8 h-8 opacity-40"/></div>
                <p className="text-[15px] font-medium text-[var(--text-secondary)]">还没有配置模型</p>
                <p className="text-[13px] mt-1">点击上方按钮添加你的第一个模型</p>
              </motion.div>
            ) : (
              <div className="space-y-3 pr-2">
                {models.map((model, idx) => (
                  <ModelCard key={model.id} model={model} onToggle={()=>onToggle(idx)} onDelete={()=>onDelete(idx)} onEdit={()=>onEdit(model)} />
                ))}
              </div>
            )}
          </AnimatePresence>
        )}
      </div>
    </div>
  )
}
