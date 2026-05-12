import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Eye, EyeOff, Brain } from 'lucide-react'
import type { Model } from '../types'

interface ModelDialogProps {
  model: Model | null;
  onClose: () => void;
  onSave: (model: Model) => void;
}

export default function ModelDialog({ model, onClose, onSave }: ModelDialogProps) {
  const [id, setId] = useState('')
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('https://api.deepseek.com')
  const [apiKey, setApiKey] = useState('')
  const [reasoning, setReasoning] = useState(false)
  const [upstreamFormat, setUpstreamFormat] = useState('openai')
  const [showKey, setShowKey] = useState(false)

  useEffect(() => {
    const values = model
      ? [model.id, model.name, model.base_url, model.api_key, model.reasoning || false, model.upstream_format || 'openai']
      : ['', '', 'https://api.deepseek.com', '', false, 'openai']
    queueMicrotask(() => {
      setId(values[0] as string)
      setName(values[1] as string)
      setBaseUrl(values[2] as string)
      setApiKey(values[3] as string)
      setReasoning(values[4] as boolean)
      setUpstreamFormat(values[5] as string)
    })
  }, [model])

  const handleSave = () => {
    if (!id.trim()) return
    onSave({
      id: id.trim(),
      name: name.trim() || id.trim(),
      base_url: baseUrl.trim().replace(/\/$/, ''),
      api_key: apiKey.trim(),
      enabled: model?.enabled || false,
      reasoning,
      upstream_format: upstreamFormat,
    })
  }

  return (
    <AnimatePresence>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
        onClick={onClose}>
        <motion.div initial={{ opacity: 0, scale: 0.97, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.97, y: 12 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
          className="bg-surface rounded-[var(--radius)] border border-[var(--border)] shadow-2xl w-full max-w-md mx-4 overflow-hidden"
          onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
            <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">{model ? '编辑模型' : '添加模型'}</h3>
            <motion.button whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }} onClick={onClose}
              className="p-1.5 rounded-[var(--radius-xs)] text-[var(--text-muted)] hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)] transition-colors duration-200">
              <X className="w-5 h-5" />
            </motion.button>
          </div>
          <div className="px-6 py-5 space-y-4">
            {[
              { label: '模型 ID', value: id, onChange: setId, placeholder: '例如: deepseek-v4-pro' },
              { label: '显示名称', value: name, onChange: setName, placeholder: '例如: DeepSeek V4 Pro' },
              { label: 'API 地址', value: baseUrl, onChange: setBaseUrl, placeholder: 'https://api.deepseek.com' },
            ].map((field) => (
              <div key={field.label}>
                <label className="block text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">{field.label}</label>
                <input type="text" value={field.value} onChange={(e)=>field.onChange(e.target.value)} placeholder={field.placeholder}
                  className="w-full px-4 py-2.5 bg-[var(--bg-primary)] border border-[var(--border)] rounded-[var(--radius-xs)] text-[var(--text-primary)] text-[14px] outline-none transition-all duration-200 focus:border-accent focus:ring-1 focus:ring-accent/20 focus:bg-surface hover:border-[var(--border-hover)]" />
              </div>
            ))}
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">API Key</label>
              <div className="relative">
                <input type={showKey ? 'text' : 'password'} value={apiKey} onChange={(e)=>setApiKey(e.target.value)} placeholder="sk-..."
                  className="w-full px-4 py-2.5 pr-10 bg-[var(--bg-primary)] border border-[var(--border)] rounded-[var(--radius-xs)] text-[var(--text-primary)] text-[14px] outline-none transition-all duration-200 focus:border-accent focus:ring-1 focus:ring-accent/20 focus:bg-surface hover:border-[var(--border-hover)]" />
                <button onClick={()=>setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors duration-200">
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-[13px] font-medium text-[var(--text-secondary)] mb-2">上游协议</label>
              <div className="flex gap-2">
                {['openai','anthropic'].map((fmt) => (
                  <button key={fmt} type="button" onClick={()=>setUpstreamFormat(fmt)}
                    className={`flex-1 py-2 px-3 rounded-[var(--radius-xs)] text-[13px] font-semibold transition-all duration-200 ${
                      upstreamFormat === fmt ? 'bg-accent text-white shadow-sm' : 'bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface-hover)] border border-[var(--border)]'
                    }`}>
                    {fmt === 'openai' ? 'OpenAI' : 'Anthropic'}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex items-center gap-3 cursor-pointer select-none">
              <button type="button" onClick={()=>setReasoning(!reasoning)}
                className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${reasoning ? 'bg-accent' : 'bg-[var(--border-hover)]'}`}>
                <motion.div animate={{ x: reasoning ? 20 : 2 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 26 }}
                  className="absolute top-[3px] w-[18px] h-[18px] rounded-full bg-white shadow-sm" />
              </button>
              <Brain className="w-4 h-4 text-[var(--text-muted)]" />
              <span className="text-[14px] text-[var(--text-primary)]">开启推理</span>
            </label>
          </div>
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[var(--border)]">
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={onClose}
              className="px-5 py-2 text-[13px] font-semibold text-[var(--text-secondary)] bg-[var(--bg-primary)] rounded-[var(--radius-xs)] hover:bg-[var(--bg-surface-hover)] transition-colors duration-200">取消</motion.button>
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={handleSave}
              className="px-5 py-2 text-[13px] font-semibold text-white bg-accent rounded-[var(--radius-xs)] hover:bg-blue-700 transition-colors duration-200 shadow-sm">保存</motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
