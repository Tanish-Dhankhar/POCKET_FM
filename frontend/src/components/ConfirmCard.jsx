import { useEffect, useState } from 'react'

export default function ConfirmCard({ initial, onConfirm, onBack, busy }) {
  const [form, setForm] = useState(initial || {})
  useEffect(() => setForm(initial || {}), [initial])
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }))

  return (
    <section className="question-card">
      <p className="eyebrow">One last look</p>
      <h2>Here’s the shape of your series.</h2>
      <p className="lead">These are inferred from your idea and answers. Adjust the production choices before we build the board.</p>
      <div className="confirm-grid">
        <div className="field"><label>Title</label><input className="input" value={form.title || ''} onChange={(e) => update('title', e.target.value)} /></div>
        <div className="field"><label>Genre</label><input className="input" value={form.genre || ''} onChange={(e) => update('genre', e.target.value)} /></div>
        <div className="field" style={{ gridColumn: '1 / -1' }}><label>Setting</label><input className="input" value={form.setting || ''} onChange={(e) => update('setting', e.target.value)} /></div>
        <div className="card">
          <div className="row between"><div><strong>Narrator</strong><div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Add a separate guiding voice</div></div><button aria-label="Toggle narrator" className={`toggle ${form.include_narrator ? 'on' : ''}`} onClick={() => update('include_narrator', !form.include_narrator)} /></div>
        </div>
        <div className="field"><label>Number of episodes</label><input className="input" type="number" min="1" max="30" value={form.ep_count || 6} onChange={(e) => update('ep_count', Number(e.target.value))} /></div>
        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <label>Average episode length — {form.ep_minutes || 10} minutes</label>
          <input type="range" min="5" max="15" value={form.ep_minutes || 10} onChange={(e) => update('ep_minutes', Number(e.target.value))} />
        </div>
      </div>
      <div className="row between" style={{ marginTop: 28 }}>
        <button className="button ghost" onClick={onBack} disabled={busy}>Back</button>
        <button className="button primary" onClick={() => onConfirm(form)} disabled={busy || !form.title?.trim()}>{busy ? 'Saving…' : 'Build my series'}</button>
      </div>
    </section>
  )
}
