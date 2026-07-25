import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as flow from '../api/flow'
import TypingText from '../components/TypingText'
import { wittyLines } from '../lib/witty'
import { useWizard } from '../store/wizard'

export default function Building() {
  const { seriesId, confirm } = useWizard()
  const navigate = useNavigate()
  const started = useRef(false)
  const [error, setError] = useState('')

  async function build() {
    setError('')
    try {
      await flow.buildSeries(seriesId, confirm)
      navigate(`/series/${seriesId}`, { replace: true })
    } catch (e) { setError(e.message); started.current = false }
  }

  useEffect(() => {
    if (!seriesId || !confirm || started.current) return
    started.current = true
    build()
  }, [seriesId]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!seriesId || !confirm) return <div className="building"><div><h2>This build session has expired.</h2><p className="muted">The saved series is still on your dashboard.</p><Link className="button primary" to="/">Back to dashboard</Link></div></div>
  return <div className="building"><div><p className="eyebrow">Building {confirm.title}</p><TypingText lines={wittyLines} /><p className="muted">Writing the series blueprint and planning each cliffhanger.</p><div className="indeterminate" />{error && <div style={{marginTop:28}}><p className="error">{error}</p><button className="button" onClick={() => { if (!started.current) { started.current = true; build() } }}>Try again</button></div>}</div></div>
}
