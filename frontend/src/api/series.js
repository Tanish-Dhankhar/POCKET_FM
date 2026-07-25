import { get, post } from './client'

export const createSeries = ({ idea, transcript = null, title = null }) =>
  post('/series', { idea, transcript, title })

export const getState = (id) => get(`/series/${id}/state`)
export const approve = (id, data = null) => post(`/series/${id}/approve`, { action: 'approve', data })
export const submit = (id, data) => post(`/series/${id}/submit`, { action: 'submit', data })
export const edit = (id, data) => post(`/series/${id}/edit`, { action: 'edit', data })
export const regenerate = (id, note) => post(`/series/${id}/regenerate`, { action: 'regenerate', note })
