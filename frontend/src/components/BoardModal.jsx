import { AnimatePresence, motion } from 'framer-motion'
import { X } from 'lucide-react'
import { useEffect } from 'react'

export default function BoardModal({open,onClose,children,wide=false}) {
  useEffect(() => { const close = (event) => event.key === 'Escape' && onClose(); if (open) window.addEventListener('keydown',close); return () => window.removeEventListener('keydown',close) },[open,onClose])
  return <AnimatePresence>{open && <motion.div className="board-modal-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onMouseDown={(e) => e.target === e.currentTarget && onClose()}><motion.div role="dialog" aria-modal="true" className={`board-modal ${wide ? 'wide' : ''}`} initial={{opacity:0,y:16,scale:.985}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:10}}><button className="modal-close" onClick={onClose} aria-label="Close"><X size={19}/></button>{children}</motion.div></motion.div>}</AnimatePresence>
}
