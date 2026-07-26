import { useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useState } from 'react'
import * as studio from '../api/studio'
import { characterKey } from '../lib/format'
import VoicePicker from './VoicePicker'

export default function CharacterCard({ seriesId, character }) {
  const [expanded, setExpanded] = useState(false)
  const [picker, setPicker] = useState(false)
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: (voiceId) => studio.patchCharacter(seriesId, characterKey(character), { voice_id: voiceId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['series', seriesId] }),
  })

  return (
    <motion.article layout className="card interactive" onClick={() => setExpanded((v) => !v)}>
      <div className="character-head">
        <div><h3 style={{ marginBottom: 5 }}>{character.name}</h3><span className="muted" style={{ fontSize: 13 }}>{character.role || 'Character'}{character.gender ? ` · ${character.gender}` : ''}</span></div>
        <span className="chip">{character.voice_id || 'No voice'}</span>
      </div>
      {expanded && <motion.dl className="character-detail" initial={{ opacity: 0 }} animate={{ opacity: 1 }} onClick={(e) => e.stopPropagation()}>
        <dt>Personality</dt><dd>{character.personality || 'Not specified yet.'}</dd>
        <dt>Details</dt><dd>{character.description || 'No additional details.'}</dd>
        <dt>Vocal direction</dt><dd>{character.vocal_signature || 'Natural delivery.'}</dd>
        {!!character.relationships?.length && <><dt>Relationships</dt><dd>{character.relationships.join(' · ')}</dd></>}
        <div className="voice-row"><div><strong style={{ fontSize: 13 }}>Voice</strong><div className="muted" style={{ fontSize: 12, marginTop: 3 }}>{mutation.isPending ? 'Saving…' : character.voice_id || 'Choose a voice'}</div></div><button className="button small" onClick={() => setPicker(true)}>Choose voice</button></div>
      </motion.dl>}
      <VoicePicker open={picker} selected={character.voice_id} onClose={() => setPicker(false)} onSelect={(voice) => { mutation.mutate(voice); setPicker(false) }} />
    </motion.article>
  )
}