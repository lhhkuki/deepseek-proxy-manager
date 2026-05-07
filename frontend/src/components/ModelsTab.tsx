import { motion } from 'framer-motion'
import { Plus } from 'lucide-react'
import ModelCard from './ModelCard'
import type { Model } from '../types'

interface ModelsTabProps {
  models: Model[];
  onToggle: (idx: number) => void;
  onDelete: (idx: number) => void;
  onEdit: (model: Model) => void;
  onAdd: () => void;
}

export default function ModelsTab({ models, onToggle, onDelete, onEdit, onAdd }: ModelsTabProps) {
  return (
    <div className="h-full flex flex-col px-4 pb-4">
      <div className="mb-3">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onAdd}
          className="flex items-center gap-2 px-4 py-2 bg-[#4A90D9] text-white text-sm font-medium rounded-lg shadow-sm hover:bg-[#3a7bc8] transition-colors"
        >
          <Plus className="w-4 h-4" />
          添加模型
        </motion.button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="space-y-3 pr-2">
          {models.map((model, idx) => (
            <ModelCard
              key={model.id}
              model={model}
              index={idx}
              onToggle={() => onToggle(idx)}
              onDelete={() => onDelete(idx)}
              onEdit={() => onEdit(model)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}