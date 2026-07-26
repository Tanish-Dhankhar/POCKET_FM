import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Download, Pause, Pencil, Play, Save, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as studio from '../api/studio'
import GenerationLoader from '../components/GenerationLoader'
import PocketLogo from '../components/PocketLogo'
import StoryPlotChart from '../components/StoryPlotChart'
import { joinEmotion, splitEmotion } from '../lib/format'

const emotions = ['Calm', 'Curious', 'Whisper', 'Fear', 'Panic', 'Anger', 'Relief', 'Joy', 'Sad', 'Excited', 'Nervous', 'Serious', 'Sarcastic', 'Tender', 'Shouting', 'Trembling', 'Pleading', 'Cold', 'Amused', 'Determined']
const bars = Array.from({ length: 180 }, (_, index) => Math.max(12, Math.min(96, 42 + Math.sin(index * 0.31) * 27 + ((index * 17) % 23) - 11)))
const stepProgress = { script: 12, evaluate: 30, voices: 48, cinematic: 84, sound: 72, mix: 88 }

function clock(seconds) {
  if (!Number.isFinite(seconds)) return '0:00'
  const whole = Math.floor(seconds)
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`
}

export default function Episode() {
  const { id, number } = useParams()
  const episodeNumber = Number(number)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const audioRef = useRef(null)
  const scrollRef = useRef(null)
  const [lines, setLines] = useState([])
  const [editing, setEditing] = useState(false)
  const [jobId, setJobId] = useState(null)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playing, setPlaying] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['episode', id, episodeNumber],
    queryFn: () => studio.getEpisode(id, episodeNumber),
    enabled: Boolean(id) && Number.isFinite(episodeNumber),
  })

  useEffect(() => {
    setLines(Array.isArray(data?.script) ? data.script : [])
  }, [data?.script])

  const save = useMutation({
    mutationFn: () => studio.putScript(id, episodeNumber, lines),
    onSuccess: async () => {
      setEditing(false)
      await queryClient.invalidateQueries({ queryKey: ['episode', id, episodeNumber] })
    },
  })
  const render = useMutation({
    mutationFn: () => studio.generateEpisode(id, episodeNumber, false),
    onSuccess: (nextJob) => setJobId(nextJob.id),
  })
  const evaluate = useMutation({
    mutationFn: () => studio.evaluateEpisode(id, episodeNumber),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['episode', id, episodeNumber] }),
  })
  const job = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => studio.getJob(jobId),
    enabled: Boolean(jobId),
    refetchInterval: (query) => ['done', 'error', 'cancelled'].includes(query.state.data?.state) ? false : 2000,
  })

  useEffect(() => {
    if (job.data?.state !== 'done') return
    queryClient.invalidateQueries({ queryKey: ['episode', id, episodeNumber] })
  }, [job.data?.state, queryClient, id, episodeNumber])

  const audio = data?.audio || {}
  const audioReady = Boolean(audio.final || audio.voices) && !audio.stale
  const segments = Array.isArray(audio.segments) ? audio.segments : []
  const offsets = Array.isArray(audio.offsets) ? audio.offsets : []
  const ratio = duration > 0 ? Math.min(1, time / duration) : 0
  const activeLine = useMemo(() => {
    const milliseconds = time * 1000
    const segment = segments.find((item) => milliseconds >= item.start_ms && milliseconds < item.end_ms)
    if (segment) return segment.line_index
    if (!offsets.length) return -1
    let index = offsets.findIndex((offset) => offset > milliseconds) - 1
    if (index < 0 && milliseconds >= offsets[offsets.length - 1]) index = offsets.length - 1
    return index
  }, [segments, offsets, time])

  useEffect(() => {
    if (activeLine < 0 || !scrollRef.current) return
    const element = scrollRef.current.children[activeLine]
    if (element) element.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [activeLine])

  function toggleAudio() {
    const element = audioRef.current
    if (!element || !audioReady) return
    if (element.paused) element.play().catch(() => setPlaying(false))
    else element.pause()
  }

  function seek(event) {
    const element = audioRef.current
    if (!element || !duration) return
    const rect = event.currentTarget.getBoundingClientRect()
    element.currentTime = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * duration
  }

  function updateLine(index, key, value) {
    setLines((current) => current.map((line, lineIndex) => lineIndex === index ? { ...line, [key]: value } : line))
  }

  function updateText(index, value) {
    const current = splitEmotion(lines[index]?.text)
    updateLine(index, 'text', joinEmotion(current.emotion, value))
  }

  function updateEmotion(index, emotion) {
    const current = splitEmotion(lines[index]?.text)
    updateLine(index, 'text', joinEmotion(emotion, current.text))
  }

  if (isLoading) return <div className="episode-loading"><div className="skeleton" /></div>
  if (error) return <div className="empty"><div><h2>Episode unavailable.</h2><p className="error">{error.message}</p><button className="button" onClick={() => navigate(`/series/${id}`)}>Back to series</button></div></div>

  const busy = render.isPending || ['queued', 'running'].includes(job.data?.state)
  if (busy) {
    const substep = job.data?.total ? (job.data.done / job.data.total) * 20 : 0
    const progress = Math.min(98, (stepProgress[job.data?.step] || 6) + substep)
    return <GenerationLoader mode="episode" message={job.data?.message || 'Starting episode production…'} progress={progress} />
  }

  const outline = data?.outline || {}
  const evaluation = data?.evaluation || {}
  const points = Array.isArray(evaluation.points) ? evaluation.points : []
  const renderError = render.error?.message || (job.data?.state === 'error' ? job.data.error : '')

  return <div className="episode-screen">
    <header className="episode-chrome">
      <button type="button" onClick={() => navigate(`/series/${id}`)}><ArrowLeft size={15} /> Back to ideaboard</button>
      <PocketLogo />
    </header>

    <main className="episode-inner">
      <div className="episode-heading">
        <p>Episode {String(episodeNumber).padStart(2, '0')}</p>
        <h1>{outline.title || `Episode ${episodeNumber}`}</h1>
      </div>

      <section className="audio-preview">
        <div className="audio-preview-head">
          <div><p>Episode preview</p><span>{audioReady ? 'Final cinematic mix' : audio.stale ? 'Audio needs to be regenerated' : 'Audio has not been generated yet'}</span></div>
          {audioReady && <a href={studio.audioUrl(id, episodeNumber)} download aria-label="Download episode audio"><Download size={15} /></a>}
        </div>
        {audioReady && <audio
          ref={audioRef}
          preload="metadata"
          src={studio.audioUrl(id, episodeNumber, audio.total_ms || Date.now())}
          onLoadedMetadata={(event) => setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : (audio.total_ms || 0) / 1000)}
          onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />}
        <div className="audio-controls">
          <button type="button" onClick={toggleAudio} disabled={!audioReady} aria-label={playing ? 'Pause episode' : 'Play episode'}>{playing ? <Pause /> : <Play />}</button>
          <div className="waveform" onClick={seek} role="slider" aria-label="Episode playback position" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(ratio * 100)}>
            {bars.map((height, index) => <span key={index} className={index / bars.length <= ratio ? 'played' : ''} style={{ height: `${height}%` }} />)}
          </div>
          <time>{clock(time)} / {clock(duration || (audio.total_ms || 0) / 1000)}</time>
          {!audioReady && <button className="render-audio" type="button" onClick={() => render.mutate()} aria-label="Generate episode audio"><Sparkles size={17} /> Generate</button>}
        </div>
        {renderError && <p className="error">{renderError}</p>}
        {job.data?.state === 'cancelled' && <p className="muted">Generation was cancelled.</p>}
      </section>

      <div className="episode-content">
        <section className="dialogue-panel">
          <div className="panel-head">
            <div><p>Dialogue timeline</p><span>{lines.length} scripted lines</span></div>
            {editing
              ? <button type="button" disabled={save.isPending} onClick={() => save.mutate()}><Save size={14} /> {save.isPending ? 'Saving…' : 'Save script'}</button>
              : <button type="button" onClick={() => setEditing(true)}><Pencil size={14} /> Edit script</button>}
          </div>
          {save.error && <p className="error" style={{ padding: '0 15px' }}>{save.error.message}</p>}
          <div className="dialogue-scroll" ref={scrollRef}>
            {lines.length === 0 && <p className="muted">No dialogue has been generated for this episode yet.</p>}
            {lines.map((line, index) => {
              const parsed = splitEmotion(line.text)
              const state = index === activeLine ? 'current' : index < activeLine ? 'played' : ''
              return <article className={`dialogue-line-card ${state}`} key={line.id || index}>
                <div className="dialogue-meta">
                  <i />
                  {editing
                    ? <><input value={line.speaker || ''} aria-label={`Speaker for line ${index + 1}`} onChange={(event) => updateLine(index, 'speaker', event.target.value)} /><select value={parsed.emotion} aria-label={`Emotion for line ${index + 1}`} onChange={(event) => updateEmotion(index, event.target.value)}><option value="">Natural</option>{emotions.map((emotion) => <option key={emotion} value={emotion}>{emotion}</option>)}</select></>
                    : <><strong>{line.speaker || 'Narrator'}</strong><span>{parsed.emotion || 'Natural'}</span></>}
                </div>
                {editing
                  ? <textarea value={parsed.text} aria-label={`Dialogue line ${index + 1}`} onChange={(event) => updateText(index, event.target.value)} />
                  : <p>{parsed.text}</p>}
              </article>
            })}
          </div>
        </section>

        <aside className="episode-side">
          <section>
            <p className="card-label">Episode outline</p>
            <p>{outline.summary || 'No episode summary is available yet.'}</p>
            {Array.isArray(outline.main_events) && outline.main_events.length > 0 && <ul>{outline.main_events.map((event, index) => <li key={index}>{event}</li>)}</ul>}
            {outline.cliffhanger && <div className="outline-cliff"><strong>Cliffhanger</strong><span>{outline.cliffhanger}</span></div>}
          </section>
          <StoryPlotChart plot={evaluation.story_plot} lineCount={lines.length} stale={evaluation.stale} />
          <section>
            <div className="judge-head"><p className="card-label">Editorial notes</p><button type="button" disabled={evaluate.isPending || !lines.length} onClick={() => evaluate.mutate()}><Sparkles size={13} /> {evaluate.isPending ? 'Reviewing…' : points.length ? 'Refresh' : 'Review'}</button></div>
            {evaluation.stale && <p className="stale-note">These notes refer to an earlier script version.</p>}
            {evaluate.error && <p className="error">{evaluate.error.message}</p>}
            {points.length > 0
              ? <ul className="judge-list">{points.map((point, index) => <li key={`${point.category}-${index}`}><i /><div><strong>{point.category}</strong><p>{point.assessment}</p>{point.suggestion && <span>{point.suggestion}</span>}</div></li>)}</ul>
              : <p>Run an editorial review to check the hook, voices, pacing, clarity, and cliffhanger.</p>}
          </section>
        </aside>
      </div>
    </main>
  </div>
}
