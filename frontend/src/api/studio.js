import { apiUrl, del, get, patch, post, put } from './client'

const list = (value) => Array.isArray(value) ? value : []

export async function listSeries() {
  const data = await get('/studio/series')
  return list(data?.series)
}

export async function getSeries(id) {
  const data = await get(`/studio/series/${id}`)
  return {
    index: data?.index || {}, input: data?.input || {}, blueprint: data?.blueprint || {},
    characters: list(data?.characters), episodes: list(data?.episodes),
  }
}

export const patchSeries = (id, data) => patch(`/studio/series/${id}`, data)
export const deleteSeries = (id) => del(`/studio/series/${id}`)
export const patchBlueprint = (id, data) => patch(`/studio/series/${id}/blueprint`, data)
export const patchCharacter = (id, key, data) => patch(`/studio/series/${id}/characters/${key}`, data)

export async function listVoices() {
  const data = await get('/studio/voices')
  return list(data?.voices)
}

export const voiceSampleUrl = (voice) => apiUrl(`/studio/voices/${encodeURIComponent(voice)}/sample`)
export const confirmCard = (id) => post(`/studio/series/${id}/confirm-card`, {})
export const saveConfirmations = (id, data) => post(`/studio/series/${id}/confirmations`, data)
export const regenerateAnalysis = (id) => post(`/studio/series/${id}/analysis/regenerate`, {})
export const refineSeries = (id, instruction) => post(`/studio/series/${id}/refine`, { instruction })
export const listEpisodes = (id) => get(`/studio/series/${id}/episodes`)
export const getEpisode = (id, number) => get(`/studio/series/${id}/episodes/${number}`)
export const putScript = (id, number, lines) => put(`/studio/series/${id}/episodes/${number}/script`, { lines })
export const putOutline = (id, number, outline) => put(`/studio/series/${id}/episodes/${number}/outline`, { outline })
export const audioUrl = (id, number, bust = '') => apiUrl(`/studio/series/${id}/episodes/${number}/audio${bust ? `?v=${bust}` : ''}`)
export const generateEpisode = (id, number, forceScript = false) =>
  post(`/studio/series/${id}/episodes/${number}/generate?force_script=${forceScript}`, {})
export const evaluateEpisode = (id, number) => post(`/studio/series/${id}/episodes/${number}/evaluate`, {})
export const getJob = (jobId) => get(`/studio/jobs/${jobId}`)

export async function transcribe(blob) {
  const form = new FormData()
  form.append('file', blob, `idea.${blob.type.includes('webm') ? 'webm' : 'wav'}`)
  return post('/studio/transcribe', form)
}

export async function uploadInputAudio(id, blob) {
  const form = new FormData()
  form.append('file', blob, `source.${blob.type.includes('webm') ? 'webm' : 'wav'}`)
  return post(`/studio/series/${id}/input/audio`, form)
}
