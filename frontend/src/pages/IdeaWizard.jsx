import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, Languages, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as flow from '../api/flow'
import * as studio from '../api/studio'
import AILoadingScreen from '../components/AILoadingScreen'
import ConfirmCard from '../components/ConfirmCard'
import QuestionCard from '../components/QuestionCard'
import { useWizard } from '../store/wizard'

const wordCount = (text) => text.trim() ? text.trim().split(/\s+/).length : 0

export default function IdeaWizard({ mode }) {
  const navigate = useNavigate()
  const wizard = useWizard()
  const [stage, setStage] = useState(mode === 'mic' ? 'record' : 'editor')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [busy, setBusy] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')
  const [recording, setRecording] = useState(false)
  const recorder = useRef(null)
  const chunks = useRef([])

  useEffect(() => { wizard.reset(mode) }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  async function beginRecording() {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio:true})
      chunks.current = []
      const media = new MediaRecorder(stream)
      recorder.current = media
      media.ondataavailable = (event) => event.data.size && chunks.current.push(event.data)
      media.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(chunks.current, {type:media.mimeType || 'audio/webm'})
        wizard.set({sourceBlob:blob}); setRecording(false); setBusy(true)
        try { const result = await studio.transcribe(blob); wizard.set({transcript:result.transcript,idea:result.transcript}); setStage('editor') }
        catch (e) { setError(e.message) } finally { setBusy(false) }
      }
      media.start(); setRecording(true)
    } catch (e) { setError(e.message || 'Microphone permission was denied.') }
  }

  function stopRecording() { if (recorder.current?.state === 'recording') recorder.current.stop() }

  async function startQuestions() {
    if (wordCount(wizard.idea) < 12) { setError('Give us a little more to work with—at least a few sentences.'); return }
    setBusy(true); setAnalyzing(true); setError('')
    try {
      const result = await flow.startSeries({idea:wizard.idea,transcript:mode === 'mic' ? wizard.transcript : null})
      const answers = result.questions.map((question) => ({question:question.question,answer:question.options?.find((option) => option.recommended)?.label || question.options?.[0]?.label || ''}))
      const card = result.confirm || {}
      wizard.set({
        seriesId:result.seriesId, questions:result.questions, answers,
        demoReplay:Boolean(result.demoReplay),
        confirm:{title:card.title || '',genre:card.genre || '',setting:card.setting || '',include_narrator:Boolean(card.narrator_suggested),ep_count:card.recommended_ep_count || 6,ep_minutes:card.recommended_ep_minutes || 10,genre_tags:card.genre_tags || [],theme_tags:card.theme_tags || []},
      })
      if (wizard.sourceBlob) studio.uploadInputAudio(result.seriesId,wizard.sourceBlob).catch(() => {})
      setQuestionIndex(0); setStage('questions')
    } catch (e) { setError(e.message) } finally { setBusy(false); setAnalyzing(false) }
  }

  async function nextQuestion() {
    if (questionIndex < wizard.questions.length - 1) { setQuestionIndex((value) => value + 1); return }
    setBusy(true); setError('')
    try {
      const review = await flow.submitAnswers(wizard.seriesId,wizard.answers)
      const blueprint = review.payload?.blueprint || {}
      // Sol has now developed the plot from the creator's answers. Reconcile the
      // preloaded card with its authoritative classifications without another call.
      wizard.set({confirm:{
        ...wizard.confirm,
        genre:blueprint.genre || wizard.confirm?.genre || '',
        setting:blueprint.setting || wizard.confirm?.setting || '',
        genre_tags:blueprint.genre_tags || wizard.confirm?.genre_tags || [],
        theme_tags:blueprint.theme_tags || wizard.confirm?.theme_tags || [],
      }})
      setStage('confirm')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function confirm(form) {
    setBusy(true); setError('')
    try {
      await studio.saveConfirmations(wizard.seriesId,form)
      wizard.set({confirm:form}); navigate('/new/building')
    } catch (e) { setError(e.message); setBusy(false) }
  }

  const answerValue = wizard.answers[questionIndex]?.answer || ''

  if (analyzing) return (
    <div className="fixed inset-0 z-[150]">
      <AILoadingScreen />
    </div>
  )

  return <section className={`idea-wizard ${mode === 'mic' ? 'voice-wizard' : ''}`}>
    <button className="corner-back" onClick={() => navigate('/new')}><ArrowLeft size={16}/> New series</button>
    {error && <p className="wizard-error">{error}</p>}
    {stage === 'record' && <motion.div className="mic-stage" initial={{opacity:0}} animate={{opacity:1}}><div><p className="eyebrow">Tell it naturally</p><h1>{recording ? 'We’re listening.' : busy ? 'Transcribing…' : 'Press when ready.'}</h1><p>Speak the complete story idea. You can edit the transcript next.</p><button className={`record ${recording ? 'recording' : ''}`} disabled={busy} onClick={recording ? stopRecording : beginRecording}><span className="record-core" /></button></div></motion.div>}
    {stage !== 'record' && <div className="writer-stage"><div className="writer-box"><textarea autoFocus value={wizard.idea} onChange={(e) => wizard.set({idea:e.target.value,transcript:mode === 'mic' ? e.target.value : wizard.transcript})} placeholder={mode === 'mic' ? 'Review and refine your transcript…' : 'Express your story in solitude…'} /><div className="writer-toolbar"><span><Languages size={15}/> EN · {wordCount(wizard.idea)} words</span><button onClick={startQuestions} disabled={busy || stage !== 'editor'}><Sparkles size={15}/>{busy ? 'Reading your idea…' : 'Send to AI'}</button></div></div></div>}
    <AnimatePresence>
      {stage === 'questions' && <motion.div className="wizard-modal-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}>
        {error && <p className="wizard-error">{error}</p>}
        <QuestionCard key={questionIndex} question={wizard.questions[questionIndex]} index={questionIndex} total={wizard.questions.length} value={answerValue} onChange={(answer) => wizard.answer(questionIndex,answer)} onBack={() => questionIndex ? setQuestionIndex((value) => value - 1) : setStage('editor')} onNext={nextQuestion} busy={busy}/>
      </motion.div>}
      {stage === 'confirm' && <motion.div className="wizard-modal-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}><motion.div className="wizard-modal" initial={{opacity:0,y:20,scale:.985}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:12}}>
        {error && <p className="notice error">{error}</p>}
        <ConfirmCard initial={wizard.confirm} onBack={() => {setQuestionIndex(wizard.questions.length - 1);setStage('questions')}} onConfirm={confirm} busy={busy}/>
      </motion.div></motion.div>}
    </AnimatePresence>
  </section>
}
