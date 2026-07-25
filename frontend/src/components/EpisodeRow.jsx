import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as studio from '../api/studio'

const labels = { planned: 'Planned', scripted: 'Scripted', voiced: 'Voiced', ready: 'Ready' }
const steps = { script: 'Writing the script', voices: 'Voicing the cast', sound: 'Choosing subtle sound', mix: 'Mixing the episode' }

export default function EpisodeRow({ seriesId, episode }) {
  const [expanded, setExpanded] = useState(false)
  const [jobId, setJobId] = useState(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const generation = useMutation({
    mutationFn: () => studio.generateEpisode(seriesId, episode.number, false),
    onSuccess: (job) => setJobId(job.id),
  })
  const job = useQuery({
    queryKey: ['job', jobId], queryFn: () => studio.getJob(jobId), enabled: Boolean(jobId),
    refetchInterval: (query) => ['done', 'error'].includes(query.state.data?.state) ? false : 2000,
  })
  const jobData = job.data
  useEffect(() => {
    if (jobData?.state === 'done') queryClient.invalidateQueries({ queryKey: ['series', seriesId] })
  }, [jobData?.state, queryClient, seriesId])
  const total = jobData?.total || 0
  const lineProgress = total ? Math.round((jobData.done / total) * 100) : 12
  const stepProgress = { script: 12, voices: Math.max(25, 25 + lineProgress * .45), sound: 80, mix: 94 }[jobData?.step] || 8
  const busy = generation.isPending || ['queued', 'running'].includes(jobData?.state)
  const ready = episode.status === 'ready' || jobData?.state === 'done'

  return (
    <article className="card episode-row">
      <div className="episode-summary" onClick={() => setExpanded((v) => !v)}>
        <span className="episode-number">{String(episode.number).padStart(2, '0')}</span>
        <div><h3 className="episode-title">{episode.title || `Episode ${episode.number}`}</h3><span className="muted" style={{ fontSize: 12 }}>{episode.emotional_focus || 'Story beat'}</span></div>
        <span className={`chip ${ready ? 'success' : ''}`}>{ready ? 'Ready' : labels[episode.status] || episode.status}</span>
      </div>
      {expanded && <div className="episode-more">
        <p>{episode.summary}</p>
        {!!episode.main_events?.length && <ul className="event-list">{episode.main_events.map((event, i) => <li key={i}>{event}</li>)}</ul>}
        {episode.cliffhanger && <p><strong>Cliffhanger:</strong> {episode.cliffhanger}</p>}
        {busy && <div className="job"><div className="row between" style={{ marginBottom: 8 }}><span>{jobData?.message || 'Starting…'}</span><span>{jobData?.step === 'voices' && total ? `${jobData.done}/${total}` : steps[jobData?.step]}</span></div><div className="job-track"><div className="job-fill" style={{ width: `${stepProgress}%` }} /></div></div>}
        {jobData?.state === 'error' && <p className="error">{jobData.error || 'Generation failed.'}</p>}
        {generation.error && <p className="error">{generation.error.message}</p>}
        <div className="row" style={{ marginTop: 14 }}>
          {ready ? <button className="button primary small" onClick={() => navigate(`/series/${seriesId}/episodes/${episode.number}`)}>Preview episode</button> : <button className="button primary small" disabled={busy} onClick={() => generation.mutate()}>{busy ? 'Generating…' : episode.status === 'planned' ? 'Generate episode' : 'Continue generation'}</button>}
        </div>
      </div>}
    </article>
  )
}
