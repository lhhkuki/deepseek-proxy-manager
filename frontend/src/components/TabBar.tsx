import { motion } from 'framer-motion'
import type { Tab } from '../types'

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

export default function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.04, ease: [0.22, 1, 0.36, 1] }}
      className="flex gap-1 px-4 py-3">
      {tabs.map((tab) => (
        <button key={tab.id} onClick={()=>onTabChange(tab.id)}
          className={`relative px-5 py-2 text-[13px] font-semibold rounded-[var(--radius-xs)] transition-colors duration-200 ${
            activeTab === tab.id ? 'text-white' : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}>
          {activeTab === tab.id && (
            <motion.div layoutId="activeTabBg"
              className="absolute inset-0 bg-accent rounded-[var(--radius-xs)] shadow-sm"
              transition={{ type: 'spring', stiffness: 320, damping: 28 }} />
          )}
          <span className="relative z-10">{tab.label}</span>
        </button>
      ))}
    </motion.div>
  )
}
