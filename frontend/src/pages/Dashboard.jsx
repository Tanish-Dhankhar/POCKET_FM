import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Link, useNavigate } from 'react-router-dom'
import * as studio from '../api/studio'
import Header from '../components/Header'
import { relativeTime } from '../lib/format'

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: series = [], isLoading, error } = useQuery({ queryKey: ['series'], queryFn: studio.listSeries })
  const remove = useMutation({ mutationFn: studio.deleteSeries, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['series'] }) })

  return <div className="shell">
    <Header action={<Link className="button primary" to="/new">New series <span>＋</span></Link>} />
    <section><p className="eyebrow">Your studio</p><h1>Stories in progress.</h1><p className="lead">Build the world once. Produce each episode when you are ready.</p></section>
    {error && <p className="error">{error.message}</p>}
    {isLoading && <div className="series-grid">{[1,2,3].map((n) => <div className="skeleton" key={n} style={{ height: 190 }} />)}</div>}
    {!isLoading && !series.length && <div className="empty"><div><h2>No series yet.</h2><p className="muted">Bring the story. We’ll help shape the season.</p><Link className="button primary" to="/new">Create your first series</Link></div></div>}
    {!!series.length && <motion.div className="series-grid" initial="hidden" animate="show" variants={{ show:{ transition:{ staggerChildren:.04 } } }}>
      {series.map((item) => <motion.article key={item.series_id} className="card interactive series-card" variants={{ hidden:{opacity:0,y:8}, show:{opacity:1,y:0} }} onClick={() => navigate(`/series/${item.series_id}`)}>
        <div><div className="row between"><span className="chip">{item.genre || 'Unclassified'}</span><button className="icon-button" title="Delete series" onClick={(e) => { e.stopPropagation(); if (window.confirm(`Delete “${item.title || 'this series'}”?`)) remove.mutate(item.series_id) }}>×</button></div><h2 className="series-title" style={{ marginTop: 22 }}>{item.title || item.logline || 'Untitled series'}</h2></div>
        <div className="series-meta"><span>{item.episode_count || item.ep_count || 0} episodes</span><span>·</span><span>{item.generated_count || 0} ready</span>{item.updated_at && <><span>·</span><span>{relativeTime(item.updated_at)}</span></>}</div>
      </motion.article>)}
    </motion.div>}
  </div>
}
