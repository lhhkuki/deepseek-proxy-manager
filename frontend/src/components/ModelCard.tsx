import { motion } from 'framer-motion'
import { Pencil, Trash2, Brain, CheckCircle2 } from 'lucide-react'
import type { Model } from '../types'

interface ModelCardProps {
  model: Model;
  onToggle: () => void;
  onDelete: () => void;
  onEdit: () => void;
}

const AVATAR_COLORS = ['#E74C3C','#3498DB','#2ECC71','#F39C12','#9B59B6','#1ABC9C','#E67E22','#34495E'];
function getAvatarColor(id: string) {
  return AVATAR_COLORS[id.split('').reduce((s,c)=>s+c.charCodeAt(0),0) % AVATAR_COLORS.length];
}

export default function ModelCard({ model, onToggle, onDelete, onEdit }: ModelCardProps) {
  const enabled = model.enabled;
  const firstLetter = (model.name || model.id || '?')[0].toUpperCase();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25 }}
      className={`bg-surface rounded-[var(--radius-sm)] border transition-all duration-200 hover:shadow-md hover:border-[var(--border-hover)] ${
        enabled ? 'border-l-[3px] border-l-success border-[var(--border)]' : 'border-[var(--border)]'
      }`}
    >
      <div className="flex items-center px-4 py-3.5 gap-3">
        <div className="w-10 h-10 rounded-[var(--radius-xs)] flex items-center justify-center text-white font-bold text-sm shrink-0" style={{backgroundColor:getAvatarColor(model.id)}}>{firstLetter}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="text-[15px] font-semibold text-[var(--text-primary)] truncate">{model.name}</div>
            {model.reasoning && <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-purple-50 text-purple-600 border border-purple-100"><Brain className="w-3 h-3"/>推理</span>}
          </div>
          <div className="text-[13px] text-accent truncate mt-0.5 font-medium">{model.base_url}</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {enabled ? (
            <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-[12px] font-semibold bg-success-soft text-success select-none"><CheckCircle2 className="w-3.5 h-3.5"/>使用中</span>
          ) : (
            <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onToggle}
              className="px-3 py-1.5 rounded-md text-[12px] font-semibold bg-[var(--bg-surface-hover)] text-[var(--text-secondary)] hover:bg-accent-soft hover:text-accent transition-colors duration-200"
            >启用</motion.button>
          )}
          <motion.button whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }} onClick={onEdit}
            className="p-2 rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors duration-200"
          ><Pencil className="w-4 h-4"/></motion.button>
          <motion.button whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.94 }} onClick={onDelete}
            className="p-2 rounded-md text-[var(--text-muted)] hover:text-danger hover:bg-danger-soft transition-colors duration-200"
          ><Trash2 className="w-4 h-4"/></motion.button>
        </div>
      </div>
    </motion.div>
  )
}
