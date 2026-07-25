import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { useRef, useState } from 'react'
import * as studio from '../api/studio'

export default function VoicePicker({ open, selected, onSelect, onClose }) {
  const { data: voices = [], isLoading } = useQuery({ queryKey: ['voices'], queryFn: studio.listVoices, enabled: open })
  const [playing, setPlaying] = useState('')
  const audioRef = useRef(null)

  function preview(voice) {
    if (audioRef.current) audioRef.current.pause()
    const audio = new Audio(studio.voiceSampleUrl(voice))
    audioRef.current = audio
    setPlaying(voice)
    audio.onended = () => setPlaying('')
    audio.onerror = () => setPlaying('')
    audio.play()
  }

  return (
    <AnimatePresence>
      {open && <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
        <motion.div className="modal" initial={{ opacity: 0, scale: .97, y: 8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: .98 }}>
          <div className="row between"><div><p className="eyebrow">Casting</p><h2 style={{ marginBottom: 0 }}>Choose a voice</h2></div><button className="icon-button" onClick={onClose}>×</button></div>
          <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>The first preview for a voice is generated and cached. It may take a moment.</p>
          <div className="voice-list">
            {isLoading && <div className="skeleton" />}
            {voices.map((voice) => <div key={voice.id} className={`voice-item ${selected === voice.id ? 'selected' : ''}`}>
              <button className="button ghost small" style={{ justifyContent: 'flex-start' }} onClick={() => onSelect(voice.id)}>{voice.id}<span className="voice-style">{voice.style}</span></button>
              <button className="icon-button" title={`Preview ${voice.id}`} onClick={() => preview(voice.id)}>{playing === voice.id ? '■' : '▶'}</button>
              {selected === voice.id && <span className="chip accent">Selected</span>}
            </div>)}
          </div>
        </motion.div>
      </motion.div>}
    </AnimatePresence>
  )
}
