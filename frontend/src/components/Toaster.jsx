import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, Info, Users, X } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { dismissToast, getToasts, subscribeToasts } from '../lib/toast'

const icons = { info: Info, warn: AlertTriangle, busy: Users }

export default function Toaster() {
  const toasts = useSyncExternalStore(subscribeToasts, getToasts, getToasts)

  return (
    <div className="toast-stack" role="status" aria-live="polite">
      <AnimatePresence initial={false}>
        {toasts.map((toast) => {
          const Icon = icons[toast.tone] || Info
          return (
            <motion.div
              key={toast.id}
              className={`toast toast-${toast.tone}`}
              initial={{ opacity: 0, y: -14, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.97 }}
              transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            >
              <span className="toast-icon"><Icon size={16} /></span>
              <div className="toast-body">
                {toast.title && <strong>{toast.title}</strong>}
                <p>{toast.message}</p>
              </div>
              <button className="toast-close" onClick={() => dismissToast(toast.id)} aria-label="Dismiss">
                <X size={14} />
              </button>
            </motion.div>
          )
        })}
      </AnimatePresence>
    </div>
  )
}
