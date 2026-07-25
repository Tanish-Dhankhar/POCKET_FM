import { useEffect, useState } from 'react'

export default function ConfirmCard({ initial, onConfirm, onBack, busy }) {
  const [form, setForm] = useState(initial || {})
  useEffect(() => setForm(initial || {}), [initial])
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))
  const updateTag = (key, index, value) =>
    update(key, (form[key] || ['', '', '', '']).map((tag, i) => (i === index ? value : tag)))

  const validTags = (() => {
    const tags = (form.genre_tags || []).map((t) => t.trim()).filter(Boolean)
    return tags.length === 4 && new Set(tags.map((t) => t.toLowerCase())).size === 4
  })()

  return (
    <section className="question-card">
      <p className="eyebrow">One last look</p>
      <h2>Here's the shape of your series.</h2>
      <p className="lead">These choices came from your idea and answers. Adjust anything before the board is built.</p>
      <div className="confirm-grid">
        <div className="field"><label>Title</label><input className="input" value={form.title || ''} onChange={(e) => update('title', e.target.value)} /></div>
        <div className="field full"><label>Setting</label><input className="input" value={form.setting || ''} onChange={(e) => update('setting', e.target.value)} /></div>
        <div className="confirm-narrator">
          <div><strong>Narrator</strong><span>Add a separate guiding voice</span></div>
          <button type="button" aria-label="Toggle narrator" className={`toggle ${form.include_narrator ? 'on' : ''}`} onClick={() => update('include_narrator', !form.include_narrator)} />
        </div>
        <div className="field"><label>Number of episodes · recommended</label><input className="input" type="number" min="1" max="30" value={form.ep_count || 6} onChange={(e) => update('ep_count', Number(e.target.value))} /></div>
        <div className="field full"><label>Average episode length · {form.ep_minutes || 10} minutes</label><input type="range" min="5" max="15" value={form.ep_minutes || 10} onChange={(e) => update('ep_minutes', Number(e.target.value))} /></div>
        <div className="field full">
          <label>Genre tags · exactly four</label>
          <div className="tag-editor">
            {(form.genre_tags || ['', '', '', '']).slice(0, 4).map((tag, index) => (
              <input key={index} className="input" value={tag} onChange={(e) => updateTag('genre_tags', index, e.target.value)} />
            ))}
          </div>
        </div>
      </div>
      <div className="question-actions">
        <button className="button ghost" onClick={onBack} disabled={busy}>Back</button>
        <button className="button primary" onClick={() => onConfirm(form)} disabled={busy || !form.title?.trim() || !validTags}>
          {busy ? 'Saving…' : 'Build my series'}
        </button>
      </div>
    </section>
  )
}
