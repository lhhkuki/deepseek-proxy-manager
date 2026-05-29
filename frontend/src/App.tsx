import { useState, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Header from './components/Header'
import TabBar from './components/TabBar'
import DashboardTab from './components/DashboardTab'
import ModelsTab from './components/ModelsTab'
import LogsTab from './components/LogsTab'
import SettingsTab from './components/SettingsTab'
import AccountsTab from './components/AccountsTab'
import ModelDialog from './components/ModelDialog'
import ConfirmDialog from './components/ConfirmDialog'
import * as api from './api'
import type { Model, LogEntry, ModelPreset } from './types'

const TABS = [
  { id: 'dashboard', label: '总览' },
  { id: 'models', label: '模型' },
  { id: 'accounts', label: '账号' },
  { id: 'logs', label: '日志' },
  { id: 'settings', label: '设置' },
]

const TAB_MOTION = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 0 },
  transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] },
}

function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [models, setModels] = useState<Model[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingModel, setEditingModel] = useState<Model | null>(null)
  const [deleteModelIndex, setDeleteModelIndex] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
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

    let statusFailures = 0
    const statusInterval = setInterval(() => {
      api.getStatus().then(s => {
        if (!cancelled) {
          setIsRunning(s.running)
          setAutostart(s.autostart)
          statusFailures = 0
        }
      }).catch(() => {
        statusFailures++
        if (statusFailures >= 3) setIsRunning(false)
      })
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
    try {
      await api.enableModel(idx)
      setModels(await api.getModels())
    } catch (e) {
      console.error('Failed to toggle model:', e)
    }
  }, [])

  const handleDeleteModel = useCallback((idx: number) => {
    setDeleteModelIndex(idx)
  }, [])

  const confirmDeleteModel = useCallback(async () => {
    if (deleteModelIndex === null) return
    try {
      await api.deleteModel(deleteModelIndex)
      setModels(await api.getModels())
      setDeleteModelIndex(null)
    } catch (e) {
      console.error('Failed to delete model:', e)
    }
  }, [deleteModelIndex])

  const handleSaveModel = useCallback(async (model: Model) => {
    try {
      const current = await api.getModels()
      const idx = current.findIndex((m: Model) => m.id === model.id)
      if (idx >= 0) current[idx] = model
      else current.push(model)
      await api.saveModels(current)
      setModels(await api.getModels())
      setDialogOpen(false)
      setEditingModel(null)
    } catch (e) {
      console.error('Failed to save model:', e)
    }
  }, [])

  const handleEditModel = useCallback((model: Model) => {
    setEditingModel(model)
    setDialogOpen(true)
  }, [])

  const handleAddModel = useCallback(() => {
    setEditingModel(null)
    setDialogOpen(true)
  }, [])

  const handleAddPreset = useCallback((preset: ModelPreset) => {
    const existing = models.find(model => model.id === preset.id)
    setEditingModel({
      id: preset.id,
      name: preset.name,
      enabled: existing?.enabled ?? models.length === 0,
      base_url: preset.base_url,
      api_key: existing?.api_key || '',
      reasoning: preset.reasoning,
      upstream_format: preset.upstream_format,
      supports_images: preset.supports_images,
    })
    setDialogOpen(true)
  }, [models])

  const handleSaveSettings = useCallback(async (newPort: number) => {
    try {
      const config = await api.getConfig()
      config.port = newPort
      await api.saveConfig(config)
      setPort(newPort)
    } catch (e) {
      console.error("Failed to save settings:", e)
      setErrorMessage("保存设置失败: " + (e instanceof Error ? e.message : String(e)))
    }
  }, [])

  const handleToggleAutostart = useCallback(async (enabled: boolean) => {
    try {
      await api.toggleAutostart(enabled)
      setAutostart(enabled)
    } catch (e) {
      console.error("Failed to toggle autostart:", e)
    }
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
      setErrorMessage('操作失败: ' + (e instanceof Error ? e.message : String(e)))
    }
  }, [isRunning])

  return (
    <div className="flex flex-col h-screen bg-[var(--bg-primary)] relative z-10">
      <Header isRunning={isRunning} autostart={autostart} onToggleAutostart={handleToggleAutostart} onToggleProxy={handleToggleProxy} />
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="flex-1 overflow-hidden relative">
        <div className={activeTab === 'dashboard' ? 'h-full' : 'hidden'}>
          <DashboardTab />
        </div>
        <AnimatePresence mode="sync">
          {activeTab === 'models' && (
            <motion.div
              key="models"
              {...TAB_MOTION}
              className="h-full"
            >
              <ModelsTab
                models={models}
                loading={loading}
                onToggle={handleToggleModel}
                onDelete={handleDeleteModel}
                onEdit={handleEditModel}
                onAdd={handleAddModel}
                onAddPreset={handleAddPreset}
              />
            </motion.div>
          )}
          {activeTab === 'logs' && (
            <motion.div
              key="logs"
              {...TAB_MOTION}
              className="h-full"
            >
              <LogsTab logs={logs} />
            </motion.div>
          )}
          {activeTab === 'accounts' && (
            <motion.div
              key="accounts"
              {...TAB_MOTION}
              className="h-full"
            >
              <AccountsTab />
            </motion.div>
          )}
          {activeTab === 'settings' && (
            <motion.div
              key="settings"
              {...TAB_MOTION}
              className="h-full"
            >
              <SettingsTab
                port={port}
                activeModelId={models.find(model => model.enabled)?.id || models[0]?.id}
                onPortChange={handleSaveSettings}
              />
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
      <ConfirmDialog
        open={deleteModelIndex !== null}
        title="删除模型"
        message={`确定删除模型「${deleteModelIndex !== null ? (models[deleteModelIndex]?.name || models[deleteModelIndex]?.id || '') : ''}」吗？这个操作只会删除本工具里的模型配置。`}
        confirmText="删除"
        danger
        onConfirm={confirmDeleteModel}
        onClose={() => setDeleteModelIndex(null)}
      />
      <ConfirmDialog
        open={Boolean(errorMessage)}
        title="操作失败"
        message={errorMessage}
        confirmText="知道了"
        cancelText=""
        onConfirm={() => setErrorMessage('')}
        onClose={() => setErrorMessage('')}
      />
    </div>
  )
}

export default App
