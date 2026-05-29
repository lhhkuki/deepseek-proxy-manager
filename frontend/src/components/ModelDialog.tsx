import { useState } from 'react'
import type { ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Eye, EyeOff, Brain, Image } from 'lucide-react'
import type { Model } from '../types'

interface ModelDialogProps {
  model: Model | null;
  onClose: () => void;
  onSave: (model: Model) => void;
}

interface TextField {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  error?: boolean;
}

export default function ModelDialog({ model, onClose, onSave }: ModelDialogProps) {
  const [id, setId] = useState(() => model?.id ?? '')
  const [name, setName] = useState(() => model?.name ?? '')
  const [baseUrl, setBaseUrl] = useState(() => model?.base_url ?? 'https://api.deepseek.com')
  const [apiKey, setApiKey] = useState(() => model?.api_key ?? '')
  const [reasoning, setReasoning] = useState(() => model?.reasoning ?? false)
  const [upstreamFormat, setUpstreamFormat] = useState(() => model?.upstream_format ?? 'openai')
  const [supportsImages, setSupportsImages] = useState(() => model?.supports_images ?? false)
  const [showKey, setShowKey] = useState(false)
  const [idError, setIdError] = useState(false)

  const handleSave = () => {
    if (!id.trim()) {
      setIdError(true)
      return
    }
    setIdError(false)
    onSave({
      id: id.trim(),
      name: name.trim() || id.trim(),
      base_url: baseUrl.trim().replace(/\/$/, ''),
      api_key: apiKey.trim(),
      enabled: model?.enabled || false,
      reasoning,
      upstream_format: upstreamFormat,
      supports_images: supportsImages,
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
            {([
              { label: '模型 ID', value: id, onChange: (v: string) => { setId(v); setIdError(false) }, placeholder: '例如: deepseek-v4-pro', error: idError },
              { label: '显示名称', value: name, onChange: setName, placeholder: '例如: DeepSeek V4 Pro' },
              { label: 'API 地址', value: baseUrl, onChange: setBaseUrl, placeholder: 'https://api.deepseek.com' },
            ] satisfies TextField[]).map((field) => (
              <div key={field.label}>
                <label className="block text-[13px] font-medium text-[var(--text-secondary)] mb-1.5">{field.label}</label>
                <input type="text" value={field.value} onChange={(e)=>field.onChange(e.target.value)} placeholder={field.placeholder}
                  className={`w-full px-4 py-2.5 bg-[var(--bg-primary)] rounded-[var(--radius-xs)] text-[var(--text-primary)] text-[14px] outline-none transition-all duration-200 focus:ring-1 focus:bg-surface ${
                    field.error
                      ? 'border border-danger focus:border-danger focus:ring-danger/20'
                      : 'border border-[var(--border)] hover:border-[var(--border-hover)] focus:border-accent focus:ring-accent/20'
                  }`} />
                {field.error && <p className="text-[12px] text-danger mt-1">模型 ID 不能为空</p>}
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <ToggleOption
                active={reasoning}
                icon={<Brain className="w-4 h-4" />}
                title="开启推理"
                detail="模型会返回推理内容时开启"
                onToggle={() => setReasoning(!reasoning)}
              />
              <ToggleOption
                active={supportsImages}
                icon={<Image className="w-4 h-4" />}
                title="支持图片输入"
                detail="模型可处理图片时开启"
                onToggle={() => setSupportsImages(!supportsImages)}
              />
            </div>
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

function ToggleOption({ active, icon, title, detail, onToggle }: { active: boolean; icon: ReactNode; title: string; detail: string; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle}
      className={`text-left rounded-[var(--radius-xs)] border p-3 transition-colors ${
        active
          ? 'border-accent bg-accent-soft'
          : 'border-[var(--border)] bg-[var(--bg-primary)] hover:bg-[var(--bg-surface-hover)]'
      }`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-[var(--text-primary)]">
          <span className={active ? 'text-accent' : 'text-[var(--text-muted)]'}>{icon}</span>
          {title}
        </div>
        <span className={`relative h-5 w-9 rounded-full transition-colors ${active ? 'bg-accent' : 'bg-[var(--border-hover)]'}`}>
          <motion.span animate={{ x: active ? 16 : 2 }}
            transition={{ type: 'spring', stiffness: 380, damping: 26 }}
            className="absolute top-[2px] h-4 w-4 rounded-full bg-white shadow-sm" />
        </span>
      </div>
      <div className="text-[11px] text-[var(--text-muted)] mt-2">{detail}</div>
    </button>
  )
}
