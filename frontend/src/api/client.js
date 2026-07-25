export const API_BASE = (import.meta.env.VITE_API_BASE || 'http://localhost:8000').replace(/\/$/, '')

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
    let detail
    try { detail = await response.json() } catch { detail = await response.text() }
    const raw = detail?.detail || detail?.message || `${response.status} ${response.statusText}`
    const message = response.status === 429
      ? 'Voice generation is rate-limited. The job will take longer; try again shortly.'
      : String(raw)
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
