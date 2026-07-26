// Minimal toast store. No dependency, no provider — the API client publishes
// from outside React, so the state has to live outside React too.
let toasts = []
const listeners = new Set()

function emit() {
  listeners.forEach((listener) => listener(toasts))
}

export function subscribeToasts(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getToasts() {
  return toasts
}

export function dismissToast(id) {
  const next = toasts.filter((toast) => toast.id !== id)
  if (next.length === toasts.length) return
  toasts = next
  emit()
}

/**
 * Show a toast. Passing a stable `id` replaces the matching toast instead of
 * stacking duplicates, so five components hitting the same limit at the same
 * moment produce one message with a fresh timer.
 */
export function showToast({ id, tone = 'info', title = '', message, duration = 6000 }) {
  const key = id || `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const existing = toasts.find((toast) => toast.id === key)
  if (existing?.timer) clearTimeout(existing.timer)

  const toast = { id: key, tone, title, message, timer: null }
  if (duration > 0) toast.timer = setTimeout(() => dismissToast(key), duration)

  toasts = existing
    ? toasts.map((item) => (item.id === key ? toast : item))
    : [...toasts, toast]
  emit()
  return key
}
