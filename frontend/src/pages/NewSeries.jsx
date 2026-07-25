import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import Header from '../components/Header'

export default function NewSeries() {
  return <div className="shell">
    <Header />
    <p className="eyebrow">New series</p><h1>How do you want to begin?</h1>
    <div className="choice-grid" style={{ marginTop: 34 }}>
      <motion.div whileHover={{ y: -5 }} transition={{ duration:.22 }}><Link className="choice" to="/new/write"><span className="choice-icon">Aa</span><h2>Write it</h2><p>Open a quiet editor and tell us the whole idea in your own words.</p></Link></motion.div>
      <motion.div whileHover={{ y: -5 }} transition={{ duration:.22 }}><Link className="choice" to="/new/mic"><span className="choice-icon">●</span><h2>Speak it</h2><p>Record the idea naturally. We’ll transcribe it before building anything.</p></Link></motion.div>
    </div>
  </div>
}
