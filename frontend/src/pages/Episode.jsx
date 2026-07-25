import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Pause, Pencil, Play, Radio, Save, Sparkles } from 'lucide-react'
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
  const {id,number} = useParams(); const episodeNumber=Number(number); const navigate=useNavigate(); const queryClient=useQueryClient()
  const audioRef=useRef(null); const [lines,setLines]=useState([]); const [editing,setEditing]=useState(false)
  const [playing,setPlaying]=useState(false); const [time,setTime]=useState(0); const [duration,setDuration]=useState(0); const [jobId,setJobId]=useState(null)
  const {data,isLoading,error} = useQuery({queryKey:['episode',id,episodeNumber],queryFn:() => studio.getEpisode(id,episodeNumber)})
  useEffect(() => { setLines((data?.script || []).map((line,index) => { const parsed=splitEmotion(line.text || ''); return {...line,id:line.id || `line-${String(index+1).padStart(4,'0')}`,text:parsed.text,emotion:line.emotion || parsed.emotion || null} })) },[data?.script])
  const save=useMutation({mutationFn:() => studio.putScript(id,episodeNumber,lines),onSuccess:() => {queryClient.invalidateQueries({queryKey:['episode',id,episodeNumber]});setEditing(false)}})
  const render=useMutation({mutationFn:() => studio.generateEpisode(id,episodeNumber,false),onSuccess:(job) => setJobId(job.id)})
  const evaluate=useMutation({mutationFn:() => studio.evaluateEpisode(id,episodeNumber),onSuccess:() => queryClient.invalidateQueries({queryKey:['episode',id,episodeNumber]})})
  const job=useQuery({queryKey:['job',jobId],queryFn:() => studio.getJob(jobId),enabled:Boolean(jobId),refetchInterval:(query) => ['done','error'].includes(query.state.data?.state) ? false : 1000})
  useEffect(() => { if (job.data?.state === 'done') {queryClient.invalidateQueries({queryKey:['episode',id,episodeNumber]});setJobId(null)} },[job.data?.state,id,episodeNumber,queryClient])

  const segments=data?.audio?.segments || []; const ratio=duration ? time/duration : 0
  const activeLine=useMemo(() => { const ms=time*1000; const found=segments.find((segment) => ms >= segment.start_ms && ms < segment.end_ms); return found?.line_index ?? -1 },[segments,time])
  const audioReady=Boolean(data?.audio?.final || data?.audio?.voices) && !data?.audio?.stale
  function toggleAudio() { const audio=audioRef.current; if (!audio) return; if (audio.paused) audio.play(); else audio.pause() }
  function seek(event) { const audio=audioRef.current; if (!audio || !duration) return; const rect=event.currentTarget.getBoundingClientRect(); audio.currentTime=Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*duration }
  function updateLine(index,key,value) { setLines((current) => current.map((line,i) => i === index ? {...line,[key]:value || (key === 'emotion' ? null : value)} : line)) }

  if (isLoading) return <div className="episode-loading"><div className="skeleton"/></div>
  if (error) return <div className="empty"><div><h2>Episode unavailable.</h2><p className="error">{error.message}</p><button className="button" onClick={() => navigate(`/series/${id}`)}>Back to series</button></div></div>
  const outline=data?.outline || {}; const evaluation=data?.evaluation || {}

  return <section className="episode-screen">
    <header className="episode-chrome"><button className="wordmark" onClick={() => navigate('/')}><Radio size={18}/> Storywave</button><button onClick={() => navigate(`/series/${id}`)}><ArrowLeft size={15}/> Idea Board</button></header>
    <div className="episode-inner"><div className="episode-heading"><p>Episode {episodeNumber} · Preview</p><h1>{outline.title || `Episode ${episodeNumber}`}</h1></div>
      <section className="audio-preview"><div className="audio-preview-head"><div><p>Audio Preview</p><span>{audioReady ? `${clock(duration)} · final mix` : data?.audio?.stale ? 'Script changed · regenerate audio' : 'Audio has not been generated'}</span></div>{audioReady && <a href={studio.audioUrl(id,episodeNumber)} download title="Download audio"><Download size={17}/></a>}</div>
        {audioReady ? <><audio ref={audioRef} preload="metadata" src={studio.audioUrl(id,episodeNumber,data?.audio?.total_ms || '')} onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)} onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => {setPlaying(false);setTime(0)}}/><div className="audio-controls"><button onClick={toggleAudio}>{playing ? <Pause fill="currentColor"/> : <Play fill="currentColor"/>}</button><div className="waveform" onClick={seek}>{bars.map((height,index) => <span key={index} className={index/bars.length <= ratio ? 'played' : ''} style={{height:`${height}%`}}/>)}</div><time>{clock(time)} / {clock(duration)}</time></div></> : <button className="episode-action render-audio" onClick={() => render.mutate()} disabled={render.isPending}><Sparkles size={14}/> {data?.audio?.stale ? 'Regenerate audio' : 'Generate audio'}</button>}
      </section>
      <div className="episode-content"><section className="dialogue-panel"><div className="panel-head"><div><p>Dialogues</p><span>{lines.length} lines · all characters</span></div><button onClick={() => editing ? save.mutate() : setEditing(true)}>{editing ? <Save size={14}/> : <Pencil size={14}/>} {editing ? 'Save script' : 'Edit'}</button></div><div className="dialogue-scroll">{lines.map((line,index) => { const current=index === activeLine; const played=segments.some((segment) => segment.line_index === index && time*1000 >= segment.end_ms); return <article id={line.id} className={`dialogue-line-card ${current ? 'current' : played ? 'played' : ''}`} aria-current={current ? 'true' : undefined} key={line.id || index}><div className="dialogue-meta">{current && <i/>}{editing ? <input value={line.speaker || ''} onChange={(e) => updateLine(index,'speaker',e.target.value)}/> : <strong>{line.speaker}</strong>}{editing ? <select value={line.emotion || ''} onChange={(e) => updateLine(index,'emotion',e.target.value)}><option value="">Natural</option>{emotions.map((emotion) => <option key={emotion}>{emotion}</option>)}</select> : line.emotion && <span>{line.emotion}</span>}</div>{editing ? <textarea value={line.text || ''} onChange={(e) => updateLine(index,'text',e.target.value)}/> : <p>{line.text}</p>}</article>})}</div>{save.error && <p className="notice error">{save.error.message}</p>}</section>
        <aside className="episode-side"><section><p className="card-label">Episode Outline</p><p>{outline.summary || 'No summary available.'}</p>{outline.main_events?.length > 0 && <ul>{outline.main_events.map((event) => <li key={event}>{event}</li>)}</ul>}{outline.cliffhanger && <div className="outline-cliff"><strong>Cliffhanger</strong><span>{outline.cliffhanger}</span></div>}</section><section><div className="judge-head"><p className="card-label">AI Evaluator Judge</p><button onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>{evaluation.points?.length ? 'Refresh' : 'Evaluate'}</button></div>{evaluation.stale && <p className="stale-note">Script changed. Refresh this evaluation.</p>}<ul className="judge-list">{(evaluation.points || []).map((point,index) => <li key={`${point.category}-${index}`}><i/><div><strong>{point.category}</strong><p>{point.assessment}</p><span>{point.suggestion}</span></div></li>)}</ul>{!evaluation.points?.length && <p className="muted">Generate the script evaluation to see focused notes on hook, pacing, voices, and cliffhanger.</p>}{evaluate.error && <p className="error">{evaluate.error.message}</p>}</section></aside>
      </div>
    </div>
    {jobId && <GenerationLoader mode="episode" message={job.data?.message || 'Preparing generation…'} progress={stepProgress[job.data?.step] || 7} error={job.data?.state === 'error' ? job.data.error : render.error?.message} onBack={() => setJobId(null)}/>} 
  </section>
}
