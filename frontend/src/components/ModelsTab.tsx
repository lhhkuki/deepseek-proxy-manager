import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, Brain, Image, Plus, ServerOff, Sparkles } from 'lucide-react'
import ModelCard from './ModelCard'
import * as api from '../api'
import type { Model, ModelPreset } from '../types'

interface ModelsTabProps {
  models: Model[];
  loading?: boolean;
  onToggle: (idx: number) => void;
  onDelete: (idx: number) => void;
  onEdit: (model: Model) => void;
  onAdd: () => void;
  onAddPreset: (preset: ModelPreset) => void;
}

export default function ModelsTab({ models, loading, onToggle, onDelete, onEdit, onAdd, onAddPreset }: ModelsTabProps) {
  const [presets, setPresets] = useState<ModelPreset[]>([])
  const [view, setView] = useState<'list' | 'presets'>('list')

  useEffect(() => {
    api.getModelPresets().then(setPresets).catch(console.error)
  }, [])

  return (
    <div className="h-full flex flex-col px-4 pb-4">
      {view === 'list' ? (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={onAdd}
            className="flex items-center gap-2 px-4 py-2.5 bg-accent text-white text-[13px] font-semibold rounded-[var(--radius-sm)] hover:bg-blue-700 transition-colors duration-200 shadow-sm">
            <Plus className="w-4 h-4" />添加模型
          </motion.button>
          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={() => setView('presets')}
            className="flex items-center gap-2 px-4 py-2.5 border border-[var(--border)] bg-surface text-[var(--text-primary)] text-[13px] font-semibold rounded-[var(--radius-sm)] hover:bg-[var(--bg-surface-hover)] transition-colors duration-200">
            <Sparkles className="w-4 h-4" />模型预设
          </motion.button>
        </div>
      ) : (
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <button type="button" onClick={() => setView('list')}
              className="p-2 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-surface-hover)] transition-colors">
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              <h2 className="text-[16px] font-semibold text-[var(--text-primary)]">选择模型预设</h2>
              <p className="text-[12px] text-[var(--text-muted)] mt-0.5">选择后进入模型配置页面，可继续调整 API Key、图片输入和推理能力。</p>
            </div>
          </div>
        </div>
      )}
      <div className="flex-1 overflow-y-auto">
        {view === 'presets' ? (
          <motion.div key="presets" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 pr-2">
            {presets.map(preset => (
              <button key={preset.id} type="button" onClick={() => onAddPreset(preset)}
                className="text-left rounded-[var(--radius-sm)] border border-[var(--border)] bg-surface p-4 hover:bg-[var(--bg-surface-hover)] hover:border-[var(--border-hover)] transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-[14px] font-semibold text-[var(--text-primary)] truncate">{preset.name}</div>
                    <div className="text-[12px] text-accent mt-1 truncate">{preset.id}</div>
                  </div>
                  <div className="flex items-center gap-1">
                    {preset.reasoning && <Brain className="w-4 h-4 text-[var(--text-muted)]" />}
                    {preset.supports_images && <Image className="w-4 h-4 text-[var(--text-muted)]" />}
                  </div>
                </div>
                <div className="text-[12px] text-[var(--text-muted)] mt-3 line-clamp-2">{preset.description}</div>
                <div className="text-[11px] text-[var(--text-muted)] mt-3 truncate">{preset.base_url}</div>
              </button>
            ))}
          </motion.div>
        ) : loading ? (
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
                <p className="text-[13px] mt-1">点击上方按钮添加第一个模型</p>
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
