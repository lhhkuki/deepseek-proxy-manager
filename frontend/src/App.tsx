import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Header from './components/Header'
import TabBar from './components/TabBar'
import ModelsTab from './components/ModelsTab'
import LogsTab from './components/LogsTab'
import SettingsTab from './components/SettingsTab'
import ModelDialog from './components/ModelDialog'
import * as api from './api'
import type { Model, LogEntry } from './types'

const TABS = [
  { id: 'models', label: '模型' },
  { id: 'logs', label: '日志' },
  { id: 'settings', label: '设置' },
]

function App() {
  const [activeTab, setActiveTab] = useState('models')
  const [models, setModels] = useState<Model[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingModel, setEditingModel] = useState<Model | null>(null)
  const [port, setPort] = useState(15800)
  const [isRunning, setIsRunning] = useState(false)
  const [autostart, setAutostart] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api.getConfig().then(cfg => {
      if (cancelled) return
      setModels(cfg.models || [])
      setPort(cfg.port || 15800)
    }).catch(e => console.error('Failed to load config:', e)).finally(() => {
      if (!cancelled) setLoading(false)
    })

    const statusInterval = setInterval(() => {
      api.getStatus().then(s => {
        if (!cancelled) {
          setIsRunning(s.running)
          setAutostart(s.autostart)
        }
      }).catch(console.error)
    }, 3000)

    return () => { cancelled = true; clearInterval(statusInterval) }
  }, [])

  useEffect(() => {
    if (activeTab !== 'logs') return
    let cancelled = false
    const doLoad = () => {
      api.getLogs().then(all => {
        if (!cancelled && all.length > 0) setLogs(all.slice(-500))
      }).catch(console.error)
    }
    doLoad()
    const interval = setInterval(doLoad, 1000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [activeTab])

  const handleToggleModel = useCallback(async (idx: number) => {
    await api.enableModel(idx)
    setModels(await api.getModels())
  }, [])

  const handleDeleteModel = useCallback(async (idx: number) => {
    if (!confirm('确定要删除这个模型吗？')) return
    await api.deleteModel(idx)
    setModels(await api.getModels())
  }, [])

  const handleSaveModel = useCallback(async (model: Model) => {
    const current = await api.getModels()
    const idx = current.findIndex((m: Model) => m.id === model.id)
    if (idx >= 0) current[idx] = model
    else current.push(model)
    await api.saveModels(current)
    setModels(await api.getModels())
    setDialogOpen(false)
    setEditingModel(null)
  }, [])

  const handleEditModel = useCallback((model: Model) => {
    setEditingModel(model)
    setDialogOpen(true)
  }, [])

  const handleAddModel = useCallback(() => {
    setEditingModel(null)
    setDialogOpen(true)
  }, [])

  const handleSaveSettings = useCallback(async (newPort: number) => {
    const config = await api.getConfig()
    config.port = newPort
    await api.saveConfig(config)
    setPort(newPort)
  }, [])

  const handleToggleAutostart = useCallback(async (enabled: boolean) => {
    await api.toggleAutostart(enabled)
    setAutostart(enabled)
  }, [])

  const handleToggleProxy = useCallback(async () => {
    try {
      if (isRunning) {
        await api.stopProxy()
      } else {
        await api.startProxy()
      }
      const status = await api.getStatus()
      setIsRunning(status.running)
    } catch (e) {
      console.error('Failed to toggle proxy:', e)
      alert('操作失败: ' + (e instanceof Error ? e.message : String(e)))
    }
  }, [isRunning])

  return (
    <div className="flex flex-col h-screen bg-[var(--bg-primary)] relative z-10">
      <Header isRunning={isRunning} autostart={autostart} onToggleAutostart={handleToggleAutostart} onToggleProxy={handleToggleProxy} />
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="flex-1 overflow-hidden relative">
        <AnimatePresence mode="wait">
          {activeTab === 'models' && (
            <motion.div
              key="models"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="h-full"
            >
              <ModelsTab
                models={models}
                loading={loading}
                onToggle={handleToggleModel}
                onDelete={handleDeleteModel}
                onEdit={handleEditModel}
                onAdd={handleAddModel}
              />
            </motion.div>
          )}
          {activeTab === 'logs' && (
            <motion.div
              key="logs"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="h-full"
            >
              <LogsTab logs={logs} />
            </motion.div>
          )}
          {activeTab === 'settings' && (
            <motion.div
              key="settings"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className="h-full"
            >
              <SettingsTab port={port} onPortChange={handleSaveSettings} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {dialogOpen && (
          <ModelDialog
            key={editingModel?.id || 'new'}
            model={editingModel}
            onClose={() => { setDialogOpen(false); setEditingModel(null) }}
            onSave={handleSaveModel}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

export default App
