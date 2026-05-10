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
    if (model) {
      setId(model.id)
      setName(model.name)
      setBaseUrl(model.base_url)
      setApiKey(model.api_key)
      setReasoning(model.reasoning || false)
      setUpstreamFormat(model.upstream_format || 'openai')
    } else {
      setId('')
      setName('')
      setBaseUrl('https://api.deepseek.com')
      setApiKey('')
      setReasoning(false)
      setUpstreamFormat('openai')
    }
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
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
          className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-[#f0f0f2]">
            <h3 className="text-lg font-bold text-[#1d1d1f]">
              {model ? '编辑模型' : '添加模型'}
            </h3>
            <motion.button
              whileHover={{ scale: 1.1 }}
              whileTap={{ scale: 0.9 }}
              onClick={onClose}
              className="p-1.5 rounded-lg text-[#6e6e73] hover:bg-[#f5f5f7] transition-colors"
            >
              <X className="w-5 h-5" />
            </motion.button>
          </div>

          {/* Form */}
          <div className="px-6 py-5 space-y-4">
            <div>
              <label className="block text-sm text-[#6e6e73] mb-1.5">模型 ID</label>
              <input
                type="text"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="例如: deepseek-v4-pro"
                className="w-full px-4 py-2.5 bg-[#f8f8f8] border border-[#e5e5e8] rounded-lg text-[#1d1d1f] text-sm focus:outline-none focus:ring-2 focus:ring-[#4A90D9]/30 focus:border-[#4A90D9] transition-all"
              />
            </div>

            <div>
              <label className="block text-sm text-[#6e6e73] mb-1.5">显示名称</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如: DeepSeek V4 Pro"
                className="w-full px-4 py-2.5 bg-[#f8f8f8] border border-[#e5e5e8] rounded-lg text-[#1d1d1f] text-sm focus:outline-none focus:ring-2 focus:ring-[#4A90D9]/30 focus:border-[#4A90D9] transition-all"
              />
            </div>

            <div>
              <label className="block text-sm text-[#6e6e73] mb-1.5">API 地址</label>
              <input
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.deepseek.com"
                className="w-full px-4 py-2.5 bg-[#f8f8f8] border border-[#e5e5e8] rounded-lg text-[#1d1d1f] text-sm focus:outline-none focus:ring-2 focus:ring-[#4A90D9]/30 focus:border-[#4A90D9] transition-all"
              />
            </div>

            <div>
              <label className="block text-sm text-[#6e6e73] mb-1.5">API Key</label>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full px-4 py-2.5 pr-10 bg-[#f8f8f8] border border-[#e5e5e8] rounded-lg text-[#1d1d1f] text-sm focus:outline-none focus:ring-2 focus:ring-[#4A90D9]/30 focus:border-[#4A90D9] transition-all"
                />
                <button
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-[#6e6e73] hover:text-[#1d1d1f] transition-colors"
                >
                  {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Upstream format */}
            <div>
              <label className="block text-sm text-[#6e6e73] mb-1.5">上游协议</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setUpstreamFormat('openai')}
                  className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    upstreamFormat === 'openai'
                      ? 'bg-[#4A90D9] text-white shadow-sm'
                      : 'bg-[#f0f0f2] text-[#6e6e73] hover:bg-[#e5e5e8]'
                  }`}
                >
                  OpenAI
                </button>
                <button
                  type="button"
                  onClick={() => setUpstreamFormat('anthropic')}
                  className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    upstreamFormat === 'anthropic'
                      ? 'bg-[#4A90D9] text-white shadow-sm'
                      : 'bg-[#f0f0f2] text-[#6e6e73] hover:bg-[#e5e5e8]'
                  }`}
                >
                  Anthropic
                </button>
              </div>
            </div>

            {/* 开启推理 */}
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <div className={`w-10 h-6 rounded-full transition-colors ${reasoning ? 'bg-[#4A90D9]' : 'bg-[#e5e5e8]'}`}>
                <div className={`w-4 h-4 rounded-full bg-white shadow-sm mt-1 transition-transform ${reasoning ? 'translate-x-5' : 'translate-x-1'}`} />
              </div>
              <input
                type="checkbox"
                checked={reasoning}
                onChange={(e) => setReasoning(e.target.checked)}
                className="hidden"
              />
              <Brain className="w-4 h-4 text-[#6e6e73]" />
              <span className="text-sm text-[#1d1d1f]">开启推理</span>
            </label>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#f0f0f2]">
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={onClose}
              className="px-5 py-2 text-sm font-medium text-[#6e6e73] bg-[#f5f5f7] rounded-lg hover:bg-[#e5e5e8] transition-colors"
            >
              取消
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleSave}
              className="px-5 py-2 text-sm font-medium text-white bg-[#4A90D9] rounded-lg hover:bg-[#3a7bc8] transition-colors shadow-sm"
            >
              保存
            </motion.button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
