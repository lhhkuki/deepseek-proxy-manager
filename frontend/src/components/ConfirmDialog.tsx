import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, X } from 'lucide-react'

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4"
          onClick={busy ? undefined : onClose}>
          <motion.div initial={{ opacity: 0, scale: 0.97, y: 12 }} animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="w-full max-w-sm overflow-hidden rounded-[var(--radius)] border border-[var(--border)] bg-surface shadow-2xl"
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-4 px-5 py-4 border-b border-[var(--border)]">
              <div className="flex items-center gap-3 min-w-0">
                <span className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-xs)] ${danger ? 'bg-danger-soft text-danger' : 'bg-accent-soft text-accent'}`}>
                  <AlertTriangle className="h-4.5 w-4.5" />
                </span>
                <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">{title}</h3>
              </div>
              <button type="button" onClick={onClose} disabled={busy}
                className="rounded-[var(--radius-xs)] p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-surface-hover)] hover:text-[var(--text-primary)] disabled:opacity-50"
                aria-label="关闭">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="px-5 py-4">
              <p className="text-[13px] leading-6 text-[var(--text-secondary)]">{message}</p>
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-4 border-t border-[var(--border)]">
              {cancelText && (
                <button type="button" onClick={onClose} disabled={busy}
                  className="px-4 py-2 rounded-[var(--radius-xs)] bg-[var(--bg-primary)] text-[13px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface-hover)] disabled:opacity-50">
                  {cancelText}
                </button>
              )}
              <button type="button" onClick={onConfirm} disabled={busy}
                className={`px-4 py-2 rounded-[var(--radius-xs)] text-[13px] font-semibold text-white shadow-sm transition-colors disabled:opacity-60 ${danger ? 'bg-danger hover:bg-red-700' : 'bg-accent hover:bg-blue-700'}`}>
                {busy ? '处理中' : confirmText}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
