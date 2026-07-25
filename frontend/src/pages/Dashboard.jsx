import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock3, MoreHorizontal, Plus, Radio } from 'lucide-react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import * as studio from '../api/studio'
import { relativeTime } from '../lib/format'

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: series = [], isLoading, error } = useQuery({ queryKey: ['series'], queryFn: studio.listSeries })
  const remove = useMutation({ mutationFn: studio.deleteSeries, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['series'] }) })

  return <section className="dashboard-screen">
    <div className="ambient-glow" />
    <div className="dashboard-inner">
      <header className="app-chrome"><button className="wordmark" onClick={() => navigate('/')}><Radio size={18} /> Storywave</button></header>
      <div className="dashboard-heading"><p className="eyebrow">Creator workspace</p><h1>Your stories</h1><p>Continue an existing story or start something new.</p></div>
      {error && <p className="notice error">{error.message}</p>}
      <motion.div className="project-grid" initial="hidden" animate="show" variants={{show:{transition:{staggerChildren:.045}}}}>
        <motion.button className="new-project-card" variants={{hidden:{opacity:0,y:10},show:{opacity:1,y:0}}} onClick={() => navigate('/new')}>
          <span className="add-project-icon"><Plus size={25} /></span><strong>Add new story</strong><small>Create a fresh project</small>
        </motion.button>
        {isLoading && [1,2,3].map((n) => <div className="project-card skeleton" key={n} />)}
        {series.map((item, index) => <motion.article
          key={item.series_id}
          className={`project-card project-accent-${index % 4}`}
          variants={{hidden:{opacity:0,y:10},show:{opacity:1,y:0}}}
          whileHover={{y:-5}}
          onClick={() => navigate(`/series/${item.series_id}`)}
        >
          <div className="project-card-wash" />
          <div className="project-top"><span>{item.genre || 'Story'}</span><button aria-label={`Delete ${item.title}`} onClick={(event) => { event.stopPropagation(); if (window.confirm(`Delete “${item.title || 'this series'}”?`)) remove.mutate(item.series_id) }}><MoreHorizontal size={18}/></button></div>
          <div className="project-bottom"><h2>{item.title || item.logline || 'Untitled series'}</h2><div><Clock3 size={12}/><span>{item.updated_at ? relativeTime(item.updated_at) : 'Just now'}</span><span>·</span><span>{item.generated_count || 0}/{item.episode_count || item.ep_count || 0} ready</span></div></div>
        </motion.article>)}
      </motion.div>
    </div>
  </section>
}
