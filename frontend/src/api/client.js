import { showToast } from '../lib/toast'

export const API_BASE = (import.meta.env.VITE_API_BASE || '/api').replace(/\/$/, '')

// Backend code for "the studio already has its maximum number of stories in
// production" — one budget shared by everyone using the product right now.
export const CAPACITY_CODE = 'story_capacity'
const RATE_LIMITED = 'Voice generation is rate-limited. The job will take longer; try again shortly.'

export class ApiError extends Error {
  constructor(message, status = 0, detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export function apiUrl(path) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

function atCapacityMessage(limit) {
  const max = Number(limit) || 5
  const stories = max === 1 ? '1 story is' : `${max} stories are`
  return `${stories} already being generated right now. Your work is saved — try again in a moment.`
}

export async function request(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const isForm = body instanceof FormData
  const response = await fetch(apiUrl(path), {
    method,
    signal,
    headers: isForm || body == null ? headers : { 'Content-Type': 'application/json', ...headers },
    body: body == null ? undefined : isForm ? body : JSON.stringify(body),
  }).catch((error) => {
    throw new ApiError(`Cannot reach the backend at ${API_BASE}. Is FastAPI running?`, 0, error)
  })

  if (!response.ok) {
    // Read the body once: a failed json() leaves the stream consumed, and a
    // proxy or dev server can answer with HTML we should never show verbatim.
    const text = await response.text().catch(() => '')
    let detail = null
    try { detail = text ? JSON.parse(text) : null } catch { detail = null }
    // FastAPI nests the payload under `detail`, which is a string for ordinary
    // errors and an object for the ones the UI needs to branch on.
    const raw = detail?.detail ?? detail?.message ?? null
    const payload = raw && typeof raw === 'object' ? raw : null
    let message = String(payload?.message || (typeof raw === 'string' && raw) || `${response.status} ${response.statusText}`)

    if (response.status === 429) {
      if (payload?.code === CAPACITY_CODE || /stories can be generated/i.test(message)) {
        message = atCapacityMessage(payload?.limit)
        showToast({
          id: CAPACITY_CODE,
          tone: 'busy',
          title: 'The studio is at capacity',
          message,
          duration: 9000,
        })
      } else {
        message = RATE_LIMITED
      }
    }
    throw new ApiError(message, response.status, detail)
  }

  if (response.status === 204) return null
  const type = response.headers.get('content-type') || ''
  return type.includes('application/json') ? response.json() : response
}

export const get = (path, options) => request(path, { ...options, method: 'GET' })
export const post = (path, body, options) => request(path, { ...options, method: 'POST', body })
export const put = (path, body, options) => request(path, { ...options, method: 'PUT', body })
export const patch = (path, body, options) => request(path, { ...options, method: 'PATCH', body })
export const del = (path, options) => request(path, { ...options, method: 'DELETE' })
