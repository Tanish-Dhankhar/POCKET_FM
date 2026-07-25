export function characterKey(character) {
  if (character?.is_narrator) return 'narrator'
  return String(character?.name || 'unnamed').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'unnamed'
}

export function relativeTime(value) {
  if (!value) return ''
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
  const units = [['year', 31536000], ['month', 2592000], ['day', 86400], ['hour', 3600], ['minute', 60]]
  for (const [unit, size] of units) if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  return 'just now'
}

export function splitEmotion(text = '') {
  const match = String(text).match(/^\[([^\]]+)]\s*/)
  return match ? { emotion: match[1], text: text.slice(match[0].length) } : { emotion: '', text }
}

export function joinEmotion(emotion, text) {
  return emotion ? `[${emotion}] ${text}` : text
}
