import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Pause, Pencil, Play, Save, Sparkles } from 'lucide-react'
import PocketLogo from '../components/PocketLogo'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as studio from '../api/studio'
import GenerationLoader from '../components/GenerationLoader'
import { splitEmotion } from '../lib/format'

const emotions = ['Calm','Curious','Whisper','Fear','Panic','Anger','Relief','Joy','Sad','Excited','Nervous','Serious','Sarcastic','Tender','Shouting','Trembling','Pleading','Cold','Amused','Determined']
const bars = Array.from({length:180},(_,i) => Math.max(12,Math.min(96,42 + Math.sin(i*.31)*27 + ((i*17)%23)-11)))
const stepProgress = {script:12,voices:42,sound:72,mix:88,evaluate:96}

function clock(seconds) { if (!Number.isFinite(seconds)) return '0:00'; const whole=Math.floor(seconds); return `${Math.floor(whole/60)}:${String(whole%60).padStart(2,'0')}` }

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
  const job = useQuery({ queryKey: ['job', jobId], queryFn: () => studio.getJob(jobId), enabled: Boolean(jobId), refetchInterval: (q) => ['done','error','cancelled'].includes(q.state.data?.state) ? false : 2000 })
  useEffect(() => { if (job.data?.state === 'done') queryClient.invalidateQueries({ queryKey: ['episode', id, episodeNumber] }) }, [job.data?.state, queryClient, id, episodeNumber])

  const segments=data?.audio?.segments || []; const ratio=duration ? time/duration : 0
  const activeLine=useMemo(() => { const ms=time*1000; const found=segments.find((segment) => ms >= segment.start_ms && ms < segment.end_ms); return found?.line_index ?? -1 },[segments,time])
  useEffect(() => { if (activeLine < 0 || !scrollRef.current) return; const el=scrollRef.current.children[activeLine]; if (el) el.scrollIntoView({behavior:'smooth',block:'nearest'}) },[activeLine])
  const audioReady=Boolean(data?.audio?.final || data?.audio?.voices) && !data?.audio?.stale
  function toggleAudio() { const audio=audioRef.current; if (!audio) return; if (audio.paused) audio.play(); else audio.pause() }
  function seek(event) { const audio=audioRef.current; if (!audio || !duration) return; const rect=event.currentTarget.getBoundingClientRect(); audio.currentTime=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*duration }
  function updateLine(index,key,value) { setLines((current) => current.map((line,i) => i === index ? {...line,[key]:value || (key === 'emotion' ? null : value)} : line)) }

  if (isLoading) return <div className="episode-loading"><div className="skeleton"/></div>
  if (error) return <div className="empty"><div><h2>Episode unavailable.</h2><p className="error">{error.message}</p><button className="button" onClick={() => navigate(`/series/${id}`)}>Back to series</button></div></div>
  const outline=data?.outline || {}; const evaluation=data?.evaluation || {}

  return <div className="episode-page">
    <div className="topbar"><Link className="brand" to={`/series/${id}`}>← <span>{outline.title || `Episode ${episodeNumber}`}</span></Link><span className={`chip ${audioReady ? 'success' : ''}`}>{audioReady ? 'Audio ready' : data?.audio?.stale ? 'Audio needs re-render' : data?.status || 'Draft'}</span></div>
    <p className="eyebrow">Episode {String(episodeNumber).padStart(2,'0')}</p><h1>{outline.title || `Episode ${episodeNumber}`}</h1><p className="lead">{outline.summary}</p>
    {audioReady && <div className="audio-player"><audio controls preload="metadata" src={studio.audioUrl(id, episodeNumber, data?.audio?.total_ms || Date.now())} /><div className="row between" style={{marginTop:8}}><span className="muted" style={{fontSize:12}}>Final mix with voices and restrained sound design</span><a className="button ghost small" href={studio.audioUrl(id, episodeNumber)} download>Download</a></div></div>}
    {!audioReady && <div className="notice" style={{margin:'24px 0'}}>{data?.audio?.stale ? 'The script changed, so the old audio was marked stale.' : 'No final audio yet.'} <button className="button primary small" style={{marginLeft:10}} disabled={busy} onClick={() => render.mutate()}>{busy ? job.data?.message || 'Rendering…' : 'Generate audio'}</button>{job.data?.state === 'error' && <span className="error"> {job.data.error}</span>}{job.data?.state === 'cancelled' && <span className="muted"> Generation cancelled.</span>}</div>}
    <div className="section-head" style={{marginTop:36}}><div><p className="eyebrow">Script</p><h2 style={{margin:0}}>{lines.length} lines</h2></div><button className="button primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? 'Saving…' : 'Save script'}</button></div>
    {save.isSuccess && <p className="notice">Saved. Existing audio is now marked stale until you re-render it.</p>}
    {save.error && <p className="error">{save.error.message}</p>}
    <div className="script-lines">{lines.map((line, index) => {
      const parsed = splitEmotion(line.text)
      return <div className="script-line" key={index}><div><input className="input speaker" value={line.speaker || ''} onChange={(e) => update(index, 'speaker', e.target.value)} /><select className="select emotion" value={parsed.emotion} onChange={(e) => updateEmotion(index, e.target.value)}><option value="">Natural</option>{['Calm','Curious','Whisper','Fear','Panic','Anger','Relief','Joy','Sad','Excited','Nervous','Serious','Sarcastic','Tender','Shouting','Trembling','Pleading','Cold','Amused','Determined'].map((tag) => <option key={tag}>{tag}</option>)}</select></div><textarea className="line-input" value={parsed.text} onChange={(e) => updateText(index, e.target.value)} /></div>
    })}</div>
  </div>
}
