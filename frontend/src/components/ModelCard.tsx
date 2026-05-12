import { motion } from 'framer-motion'
import { Pencil, Trash2, Brain } from 'lucide-react'
import type { Model } from '../types'

interface ModelCardProps {
  model: Model;
  index: number;
  onToggle: () => void;
  onDelete: () => void;
  onEdit: () => void;
}

const AVATAR_COLORS = [
  '#E74C3C', '#3498DB', '#2ECC71', '#F39C12',
  '#9B59B6', '#1ABC9C', '#E67E22', '#34495E'
];

function getAvatarColor(id: string): string {
  const idx = id.split('').reduce((sum, c) => sum + c.charCodeAt(0), 0) % AVATAR_COLORS.length;
  return AVATAR_COLORS[idx];
}

export default function ModelCard({ model, index, onToggle, onDelete, onEdit }: ModelCardProps) {
  const enabled = model.enabled;
  const avatarColor = getAvatarColor(model.id);
  const firstLetter = (model.name || model.id || '?')[0].toUpperCase();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3, delay: index * 0.05, ease: [0.4, 0, 0.2, 1] }}
      whileHover={{ y: -2, transition: { duration: 0.2 } }}
      className={`bg-white rounded-xl shadow-sm transition-shadow duration-200 hover:shadow-md ${
        enabled ? 'border-l-[3px] border-l-[#34c759] pl-[13px] pr-4 py-4' : 'p-4'
      }`}
    >
      <div className="flex items-center">
        {/* Avatar */}
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold text-sm shrink-0"
          style={{ backgroundColor: avatarColor }}
        >
          {firstLetter}
        </div>

        {/* Info */}
        <div className="ml-3 flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="text-[15px] font-bold text-[#1d1d1f] truncate">{model.name}</div>
            {model.reasoning && (
              <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-purple-50 text-purple-600">
                <Brain className="w-3 h-3" />
                推理
              </span>
            )}
          </div>
          <div className="text-[13px] text-[#4A90D9] truncate mt-0.5">{model.base_url}</div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 ml-4 shrink-0">
          {/* Toggle Button */}
          {enabled ? (
            <span className="px-4 py-1.5 rounded-lg text-sm font-medium bg-[#e5e5e8] text-[#9e9e9e] cursor-default select-none">
              使用中
            </span>
          ) : (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onToggle}
              className="px-4 py-1.5 rounded-lg text-sm font-medium bg-[#f0f0f2] text-[#6e6e73] hover:bg-[#e5e5e8] transition-colors"
            >
              启用
            </motion.button>
          )}

          {/* Edit */}
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={onEdit}
            className="p-2 rounded-lg text-[#6e6e73] hover:bg-[#f5f5f7] transition-colors"
          >
            <Pencil className="w-4 h-4" />
          </motion.button>

          {/* Delete */}
          <motion.button
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            onClick={onDelete}
            className="p-2 rounded-lg text-[#c0c0c0] hover:text-[#ff3b30] hover:bg-[#fff5f5] transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </motion.button>
        </div>
      </div>
    </motion.div>
  )
}
