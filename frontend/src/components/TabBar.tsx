import { motion } from 'framer-motion'

interface Tab {
  id: string;
  label: string;
}

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

export default function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.1, ease: [0.4, 0, 0.2, 1] }}
      className="flex gap-1 px-4 py-3"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`relative px-5 py-2 text-sm font-medium rounded-lg transition-colors duration-200 ${
            activeTab === tab.id
              ? 'text-[#1d1d1f]'
              : 'text-[#6e6e73] hover:text-[#1d1d1f]'
          }`}
        >
          {activeTab === tab.id && (
            <motion.div
              layoutId="activeTab"
              className="absolute inset-0 bg-white rounded-lg shadow-sm"
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-10">{tab.label}</span>
        </button>
      ))}
    </motion.div>
  )
}