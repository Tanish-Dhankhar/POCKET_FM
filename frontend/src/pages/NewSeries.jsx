import { ArrowLeft, Mic2, PenLine } from 'lucide-react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'

const choices = [
  { path: '/new/write', icon: PenLine, label: 'Write', copy: 'Open a quiet editor and describe the world, conflict, and people in your story.' },
  { path: '/new/mic', icon: Mic2, label: 'Speak', copy: 'Record the idea naturally. You can review the transcript before anything is generated.' },
]

export default function NewSeries() {
  const navigate = useNavigate()
  return <section className="choice-screen">
    <button className="corner-back" onClick={() => navigate('/')}><ArrowLeft size={16}/> Dashboard</button>
    <div className="choice-copy"><p className="eyebrow">New series</p><h1>How does the story arrive?</h1><p>Start with the format that feels natural. Both paths lead to the same guided story studio.</p></div>
    <div className="choice-tiles">
      {choices.map(({path,icon:Icon,label,copy}) => <motion.button key={path} className="choice-tile" whileHover={{y:-6}} whileTap={{scale:.98}} onClick={() => navigate(path)}>
        <span className="choice-icon"><Icon size={46} strokeWidth={1.25}/></span><div><h2>{label}</h2><p>{copy}</p></div><span className="choice-arrow">↗</span>
      </motion.button>)}
    </div>
  </section>
}
