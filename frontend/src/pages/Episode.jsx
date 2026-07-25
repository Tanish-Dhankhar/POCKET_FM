import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as studio from '../api/studio'
import { joinEmotion, splitEmotion } from '../lib/format'

export default function Episode() {
  const { id, number } = useParams()
  const episodeNumber = Number(number)
  const queryClient = useQueryClient()
  const [lines, setLines] = useState([])
  const [jobId, setJobId] = useState(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['episode', id, episodeNumber], queryFn: () => studio.getEpisode(id, episodeNumber) })
  useEffect(() => { setLines(Array.isArray(data?.script) ? data.script : []) }, [data?.script])
  const save = useMutation({ mutationFn: () => studio.putScript(id, episodeNumber, lines), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episode', id, episodeNumber] }) })
  const render = useMutation({ mutationFn: () => studio.generateEpisode(id, episodeNumber, false), onSuccess: (job) => setJobId(job.id) })
  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => studio.getJob(jobId), enabled: Boolean(jobId), refetchInterval: (q) => ['done','error'].includes(q.state.data?.state) ? false : 2000 })
  useEffect(() => { if (job.data?.state === 'done') queryClient.invalidateQueries({ queryKey: ['episode', id, episodeNumber] }) }, [job.data?.state, queryClient, id, episodeNumber])

  function update(index, field, value) {
    setLines((current) => current.map((line, i) => i === index ? { ...line, [field]: value } : line))
  }
  function updateText(index, value) {
    const parsed = splitEmotion(lines[index]?.text)
    update(index, 'text', joinEmotion(parsed.emotion, value))
  }
  function updateEmotion(index, value) {
    const parsed = splitEmotion(lines[index]?.text)
    update(index, 'text', joinEmotion(value, parsed.text))
  }

  if (isLoading) return <div className="episode-page"><div className="skeleton" style={{height:250}} /></div>
  if (error) return <div className="empty"><div><h2>Episode unavailable.</h2><p className="error">{error.message}</p><Link className="button" to={`/series/${id}`}>Back to series</Link></div></div>
  const outline = data?.outline || {}
  const audioReady = Boolean(data?.audio?.final || data?.audio?.voices) && !data?.audio?.stale
  const busy = ['queued','running'].includes(job.data?.state) || render.isPending

  return <div className="episode-page">
    <div className="topbar"><Link className="brand" to={`/series/${id}`}>← <span>{outline.title || `Episode ${episodeNumber}`}</span></Link><span className={`chip ${audioReady ? 'success' : ''}`}>{audioReady ? 'Audio ready' : data?.audio?.stale ? 'Audio needs re-render' : data?.status || 'Draft'}</span></div>
    <p className="eyebrow">Episode {String(episodeNumber).padStart(2,'0')}</p><h1>{outline.title || `Episode ${episodeNumber}`}</h1><p className="lead">{outline.summary}</p>
    {audioReady && <div className="audio-player"><audio controls preload="metadata" src={studio.audioUrl(id, episodeNumber, data?.audio?.total_ms || Date.now())} /><div className="row between" style={{marginTop:8}}><span className="muted" style={{fontSize:12}}>Final mix with voices and restrained sound design</span><a className="button ghost small" href={studio.audioUrl(id, episodeNumber)} download>Download</a></div></div>}
    {!audioReady && <div className="notice" style={{margin:'24px 0'}}>{data?.audio?.stale ? 'The script changed, so the old audio was marked stale.' : 'No final audio yet.'} <button className="button primary small" style={{marginLeft:10}} disabled={busy} onClick={() => render.mutate()}>{busy ? job.data?.message || 'Rendering…' : 'Generate audio'}</button>{job.data?.state === 'error' && <span className="error"> {job.data.error}</span>}</div>}
    <div className="section-head" style={{marginTop:36}}><div><p className="eyebrow">Script</p><h2 style={{margin:0}}>{lines.length} lines</h2></div><button className="button primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save script'}</button></div>
    {save.isSuccess && <p className="notice">Saved. Existing audio is now marked stale until you re-render it.</p>}
    {save.error && <p className="error">{save.error.message}</p>}
    <div className="script-lines">{lines.map((line, index) => {
      const parsed = splitEmotion(line.text)
      return <div className="script-line" key={index}><div><input className="input speaker" value={line.speaker || ''} onChange={(e) => update(index, 'speaker', e.target.value)} /><select className="select emotion" value={parsed.emotion} onChange={(e) => updateEmotion(index, e.target.value)}><option value="">Natural</option>{['Calm','Curious','Whisper','Fear','Panic','Anger','Relief','Joy','Sad','Excited','Nervous','Serious','Sarcastic','Tender','Shouting','Trembling','Pleading','Cold','Amused','Determined'].map((tag) => <option key={tag}>{tag}</option>)}</select></div><textarea className="line-input" value={parsed.text} onChange={(e) => updateText(index, e.target.value)} /></div>
    })}</div>
  </div>
}
