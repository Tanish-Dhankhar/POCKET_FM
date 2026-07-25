import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as flow from '../api/flow'
import * as studio from '../api/studio'
import ConfirmCard from '../components/ConfirmCard'
import QuestionCard from '../components/QuestionCard'
import { useWizard } from '../store/wizard'

function wordCount(text) { return text.trim() ? text.trim().split(/\s+/).length : 0 }

export default function IdeaWizard({ mode }) {
  const navigate = useNavigate()
  const wizard = useWizard()
  const [stage, setStage] = useState(mode === 'mic' ? 'record' : 'editor')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [recording, setRecording] = useState(false)
  const recorder = useRef(null)
  const chunks = useRef([])

  useEffect(() => { wizard.reset(mode) }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  async function beginRecording() {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunks.current = []
      const media = new MediaRecorder(stream)
      recorder.current = media
      media.ondataavailable = (event) => event.data.size && chunks.current.push(event.data)
      media.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(chunks.current, { type: media.mimeType || 'audio/webm' })
        wizard.set({ sourceBlob: blob })
        setRecording(false)
        setBusy(true)
        try {
          const result = await studio.transcribe(blob)
          wizard.set({ transcript: result.transcript, idea: result.transcript })
          setStage('editor')
        } catch (e) { setError(e.message) }
        finally { setBusy(false) }
      }
      media.start()
      setRecording(true)
    } catch (e) { setError(e.message || 'Microphone permission was denied.') }
  }

  function stopRecording() { recorder.current?.state === 'recording' && recorder.current.stop() }

  async function startQuestions() {
    if (wordCount(wizard.idea) < 12) { setError('Give us a little more to work with — at least a few sentences.'); return }
    setBusy(true); setError('')
    try {
      const result = await flow.startSeries({ idea: wizard.idea, transcript: mode === 'mic' ? wizard.transcript : null })
      const answers = result.questions.map((question) => ({ question: question.question, answer: question.options?.find((o) => o.recommended)?.label || question.options?.[0]?.label || '' }))
      wizard.set({ seriesId: result.seriesId, questions: result.questions, answers })
      if (wizard.sourceBlob) studio.uploadInputAudio(result.seriesId, wizard.sourceBlob).catch(() => {})
      setQuestionIndex(0); setStage('questions')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  async function nextQuestion() {
    if (questionIndex < wizard.questions.length - 1) { setQuestionIndex((v) => v + 1); return }
    setBusy(true); setError('')
    try {
      await flow.submitAnswers(wizard.seriesId, wizard.answers)
      const card = await studio.confirmCard(wizard.seriesId)
      wizard.set({ confirm: {
        title: card.title, genre: card.genre, setting: card.setting,
        include_narrator: Boolean(card.narrator_suggested),
        ep_count: card.recommended_ep_count, ep_minutes: card.recommended_ep_minutes,
      }})
      setStage('confirm')
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  async function confirm(form) {
    setBusy(true); setError('')
    try {
      await Promise.all([
        studio.patchSeries(wizard.seriesId, { title: form.title, include_narrator: form.include_narrator, ep_count: form.ep_count, ep_minutes: form.ep_minutes }),
        studio.patchBlueprint(wizard.seriesId, { genre: { genre: form.genre, setting: form.setting } }),
      ])
      wizard.set({ confirm: form })
      navigate('/new/building')
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const answerValue = wizard.answers[questionIndex]?.answer || ''
  return <div className="wizard reading">
    <div className="wizard-head"><Link className="brand" to="/"><span className="brand-mark">◒</span><span>Storywave</span></Link><div className="progress">{['editor','questions','confirm'].map((item) => <span key={item} className={stage === item || (stage === 'record' && item === 'editor') ? 'active' : ''} />)}</div></div>
    {error && <p className="notice error">{error}</p>}
    <AnimatePresence mode="wait">
      {stage === 'record' && <motion.section key="record" className="mic-stage" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}><div><p className="eyebrow">Tell it naturally</p><h1>{recording ? 'We’re listening.' : busy ? 'Transcribing…' : 'Press when ready.'}</h1><p className="muted">Speak the complete story idea. You can edit the transcript next.</p><button className={`record ${recording ? 'recording' : ''}`} disabled={busy} onClick={recording ? stopRecording : beginRecording}><span className="record-core" /></button></div></motion.section>}
      {stage === 'editor' && <motion.section key="editor" initial={{opacity:0,x:16}} animate={{opacity:1,x:0}} exit={{opacity:0,x:-12}}>
        <p className="eyebrow">{mode === 'mic' ? 'Review the transcript' : 'Your story idea'}</p>
        <textarea className="idea-editor" autoFocus value={wizard.idea} onChange={(e) => wizard.set({ idea: e.target.value, transcript: mode === 'mic' ? e.target.value : wizard.transcript })} placeholder="Tell us the whole idea — the world, the conflict, the people, and what makes you want to hear what happens next…" />
        <div className="row between"><span className="muted" style={{fontSize:12}}>{wordCount(wizard.idea)} words</span><button className="button primary" onClick={startQuestions} disabled={busy}>{busy ? 'Reading your idea…' : 'Next'}</button></div>
      </motion.section>}
      {stage === 'questions' && <QuestionCard key={`q-${questionIndex}`} question={wizard.questions[questionIndex]} index={questionIndex} total={wizard.questions.length} value={answerValue} onChange={(answer) => wizard.answer(questionIndex, answer)} onBack={() => questionIndex ? setQuestionIndex((v) => v - 1) : setStage('editor')} onNext={nextQuestion} busy={busy} />}
      {stage === 'confirm' && <motion.div key="confirm" initial={{opacity:0,x:16}} animate={{opacity:1,x:0}}><ConfirmCard initial={wizard.confirm} onBack={() => { setQuestionIndex(wizard.questions.length - 1); setStage('questions') }} onConfirm={confirm} busy={busy} /></motion.div>}
    </AnimatePresence>
  </div>
}
