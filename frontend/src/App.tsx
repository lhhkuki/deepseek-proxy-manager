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

  // Load initial data
  useEffect(() => {
    loadData()
    const interval = setInterval(() => {
      loadLogs()
      loadStatus()
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const loadData = async () => {
    try {
      const config = await api.getConfig()
      setModels(config.models || [])
      setPort(config.port || 15800)
    } catch (e) {
      console.error('Failed to load config:', e)
    }
  }

  const loadLogs = async () => {
    try {
      const newLogs = await api.getLogs()
      if (newLogs.length > 0) {
        setLogs(prev => [...prev, ...newLogs].slice(-500))
      }
    } catch (e) {
      console.error('Failed to load logs:', e)
    }
  }

  const loadStatus = async () => {
    try {
      const status = await api.getStatus()
      setIsRunning(status.running)
      setAutostart(status.autostart)
    } catch (e) {
      console.error('Failed to load status:', e)
    }
  }

  const handleToggleModel = useCallback(async (idx: number) => {
    await api.enableModel(idx)
    const updated = await api.getModels()
    setModels(updated)
  }, [])

  const handleDeleteModel = useCallback(async (idx: number) => {
    if (!confirm('确定要删除这个模型吗？')) return
    await api.deleteModel(idx)
    const updated = await api.getModels()
    setModels(updated)
  }, [])

  const handleSaveModel = useCallback(async (model: Model) => {
    const current = await api.getModels()
    const idx = current.findIndex((m: Model) => m.id === model.id)
    if (idx >= 0) {
      current[idx] = model
    } else {
      current.push(model)
    }
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
    if (isRunning) {
      await api.stopProxy()
    } else {
      await api.startProxy()
    }
    setIsRunning(!isRunning)
  }, [isRunning])

  return (
    <div className="flex flex-col h-screen bg-[#f5f5f7]">
      <Header isRunning={isRunning} autostart={autostart} onToggleAutostart={handleToggleAutostart} onToggleProxy={handleToggleProxy} />
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="flex-1 overflow-hidden relative">
        <AnimatePresence mode="wait">
          {activeTab === 'models' && (
            <motion.div
              key="models"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
              className="h-full"
            >
              <ModelsTab
                models={models}
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
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
              className="h-full"
            >
              <LogsTab logs={logs} />
            </motion.div>
          )}
          {activeTab === 'settings' && (
            <motion.div
              key="settings"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
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
