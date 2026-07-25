import { motion } from 'framer-motion'
import { Check } from 'lucide-react'
import { useEffect, useState } from 'react'

export default function QuestionCard({ question, index, total, value, onChange, onNext, onBack, busy }) {
  const recommended = question?.options?.find((option) => option.recommended)?.label || question?.options?.[0]?.label || ''
  const [custom, setCustom] = useState('')
  useEffect(() => setCustom(''), [index])
  const selected = value || recommended
  return <motion.section className="question-card" initial={{opacity:0,x:18}} animate={{opacity:1,x:0}}>
    <p className="eyebrow">Question {index + 1} of {total}</p><h2>{question?.question}</h2>
    <div className="option-list">{(question?.options || []).map((option) => <button key={option.label} className={`option ${selected === option.label ? 'selected' : ''}`} onClick={() => { setCustom(''); onChange(option.label) }}>
      <span><strong>{option.label}</strong><p>{option.detail}</p></span><span className="option-status">{option.recommended && <em>Recommended</em>}{selected === option.label && <Check size={17}/>}</span>
    </button>)}</div>
    <div className="field"><label>Or write your own answer</label><input className="input" value={custom} placeholder="Something more specific…" onChange={(event) => { setCustom(event.target.value); onChange(event.target.value || recommended) }} /></div>
    <div className="question-actions"><button className="button ghost" onClick={onBack} disabled={busy}>Back</button><button className="button primary" onClick={onNext} disabled={!selected || busy}>{busy ? 'Thinking…' : index === total - 1 ? 'Review story' : 'Next'}</button></div>
  </motion.section>
}
