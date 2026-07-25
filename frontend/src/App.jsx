import { AnimatePresence, motion } from 'framer-motion'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import NewSeries from './pages/NewSeries'
import IdeaWizard from './pages/IdeaWizard'
import Building from './pages/Building'
import Ideaboard from './pages/Ideaboard'
import Episode from './pages/Episode'

const page = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -5 },
  transition: { duration: 0.24, ease: [0.22, 1, 0.36, 1] },
}

function Frame({ children }) {
  return <motion.main className="page" {...page}>{children}</motion.main>
}

export default function App() {
  const location = useLocation()
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/" element={<Frame><Dashboard /></Frame>} />
        <Route path="/new" element={<Frame><NewSeries /></Frame>} />
        <Route path="/new/write" element={<Frame><IdeaWizard mode="write" /></Frame>} />
        <Route path="/new/mic" element={<Frame><IdeaWizard mode="mic" /></Frame>} />
        <Route path="/new/building" element={<Frame><Building /></Frame>} />
        <Route path="/series/:id" element={<Frame><Ideaboard /></Frame>} />
        <Route path="/series/:id/episodes/:number" element={<Frame><Episode /></Frame>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AnimatePresence>
  )
}
