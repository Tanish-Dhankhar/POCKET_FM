import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Check, ChevronDown, Loader2, Pencil, RefreshCw, Sparkles, UserRound, X } from 'lucide-react'
import PocketLogo from '../components/PocketLogo'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as studio from '../api/studio'
import AILoadingScreen from '../components/AILoadingScreen'
import IdeaRefiningLoader from '../components/IdeaRefiningLoader'
import GenreRadar from '../components/GenreRadar'
import ThemeBars from '../components/ThemeBars'
import EmotionalCurveChart from '../components/EmotionalCurveChart'
import VoicePicker from '../components/VoicePicker'
import { characterKey } from '../lib/format'

/* ── pocketFM-style card base ── */
const card =
  'rounded-xl border border-neutral-800 bg-[#0A0A0A] transition-colors hover:border-red-900/80 hover:bg-neutral-900'

/* ── SWOT quadrant config ── */
const QUAD_CONFIG = [
  { key: 'strengths',    label: 'Strengths',    letter: 'S', color: 'text-green-400', ring: 'border-green-500/40', bg: 'bg-green-500/10', accent: 'bg-green-400', badge: 'bg-green-400/15' },
  { key: 'weaknesses',   label: 'Weaknesses',   letter: 'W', color: 'text-red-400',   ring: 'border-red-500/40',   bg: 'bg-red-500/10',   accent: 'bg-red-400',   badge: 'bg-red-400/15' },
  { key: 'opportunities',label: 'Opportunities',letter: 'O', color: 'text-blue-400',  ring: 'border-blue-500/40',  bg: 'bg-blue-500/10',  accent: 'bg-blue-400',  badge: 'bg-blue-400/15' },
  { key: 'threats',      label: 'Threats',      letter: 'T', color: 'text-amber-400', ring: 'border-amber-500/40', bg: 'bg-amber-500/10', accent: 'bg-amber-400', badge: 'bg-amber-400/15' },
]

/* ── Primitives ── */
function Modal({ open, onClose, children, size = 'md', tall = false, leaveChatBar = false }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  const maxW =
    size === '70vw' ? 'w-[70vw] max-w-[70vw]' :
    size === '4xl'  ? 'max-w-4xl' :
    size === '6xl'  ? 'max-w-6xl' :
    size === '5xl'  ? 'max-w-5xl' :
    size === '3xl'  ? 'max-w-3xl' :
    size === '2xl'  ? 'max-w-2xl' :
    size === 'lg'   ? 'max-w-lg'  : 'max-w-xl'

  return (
    <div
      className={`fixed inset-0 z-[80] flex justify-center p-4 ${leaveChatBar ? 'items-start pt-10 pb-28 sm:pt-14 sm:pb-32' : 'items-center'}`}
      onClick={onClose}
    >
      <div className={`absolute inset-0 bg-black/85 ${leaveChatBar ? 'bottom-24 sm:bottom-28' : ''}`} />
      <div
        onClick={(e) => e.stopPropagation()}
        className={`relative z-10 w-full ${maxW} overflow-y-auto rounded-xl border border-neutral-800 bg-[#0A0A0A] p-6 sm:p-8 ${
          tall
            ? leaveChatBar
              ? 'min-h-[60vh] max-h-[calc(100vh-11rem)]'
              : 'min-h-[75vh] max-h-[92vh]'
            : 'max-h-[85vh]'
        }`}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 z-20 rounded-md p-1.5 text-neutral-500 transition-colors hover:bg-neutral-900 hover:text-white"
          aria-label="Close"
        >
          <X className="h-4 w-4" strokeWidth={2} />
        </button>
        {children}
      </div>
    </div>
  )
}

function CardHeading({ children }) {
  return (
    <h3
      className="text-2xl font-bold tracking-widest text-white uppercase"
      style={{ fontFamily: '"JetBrains Mono", monospace' }}
    >
      {children}
    </h3>
  )
}

function EditIconButton({ label, editing, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border p-2 transition-colors ${
        editing
          ? 'border-[#E61C38]/60 bg-[#E61C38]/10 text-[#E61C38]'
          : 'border-neutral-800 text-neutral-400 hover:border-[#E61C38]/60 hover:text-white'
      }`}
      aria-label={label}
      title={label}
    >
      {editing
        ? <Check className="h-3.5 w-3.5" strokeWidth={2} />
        : <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />}
    </button>
  )
}

const TAG_COLORS = {
  blue:    'border-blue-500/30   text-blue-400',
  red:     'border-red-500/30    text-red-400',
  orange:  'border-orange-500/30 text-orange-400',
  purple:  'border-purple-500/30 text-purple-400',
  green:   'border-green-500/30  text-green-400',
  neutral: 'border-neutral-700   text-neutral-300',
}
const TAG_CYCLE = ['blue', 'purple', 'red', 'orange', 'green', 'neutral']

function Tag({ label, color = 'neutral' }) {
  const cls = TAG_COLORS[color] ?? TAG_COLORS.neutral
  return (
    <span className={`inline-flex items-center rounded-full border bg-neutral-900 px-3 py-1 text-xs font-medium ${cls}`}>
      {label}
    </span>
  )
}

/* ── Main page ── */
export default function Ideaboard() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [modal, setModal] = useState(null)
  const [openEpisode, setOpenEpisode] = useState(1)
  const [activeCharacter, setActiveCharacter] = useState(null)
  const [picker, setPicker] = useState(false)
  const [characterDraft, setCharacterDraft] = useState(null)
  const [editingCharacter, setEditingCharacter] = useState(false)
  const [plotDraft, setPlotDraft] = useState(null)
  const [editingStory, setEditingStory] = useState(false)
  const [editingSetting, setEditingSetting] = useState(false)
  const [refinePrompt, setRefinePrompt] = useState('')
  const [episodeJob, setEpisodeJob] = useState(null)
  const [analysisJob, setAnalysisJob] = useState(null)
  const [curveJob, setCurveJob] = useState(null)
  const [curveError, setCurveError] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['series', id],
    queryFn: () => studio.getSeries(id),
    refetchInterval: 15000,
  })

  const generation = useMutation({
    mutationFn: (number) => studio.generateEpisode(id, number, false),
    onSuccess: (job, number) => setEpisodeJob({ id: job.id, number }),
  })
  const refine = useMutation({
    mutationFn: () => studio.refineSeries(id, refinePrompt),
    onSuccess: (job) => navigate(`/series/${id}/refining?job=${job.id}`),
  })
  const saveBlueprint = useMutation({
    mutationFn: (payload) => studio.patchBlueprint(id, payload),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['series', id] }); setModal(null) },
  })
  const saveCharacter = useMutation({
    mutationFn: (draft) => studio.patchCharacter(id, characterKey(activeCharacter), draft),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['series', id] })
      setEditingCharacter(false)
      setActiveCharacter(null)
    },
  })
  const chooseVoice = useMutation({
    mutationFn: (voice) => studio.patchCharacter(id, characterKey(activeCharacter), { voice_id: voice }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['series', id] }),
  })
  const regenerateAnalysis = useMutation({
    mutationFn: () => studio.regenerateAnalysis(id),
    onSuccess: (job) => setAnalysisJob(job.id),
  })
  const regenerateCurve = useMutation({
    mutationFn: () => studio.regenerateEmotionalCurve(id),
    onSuccess: (job) => { setCurveError(''); setCurveJob(job.id) },
    onError: (err) => setCurveError(err.message || 'Could not start emotional curve generation.'),
  })

  const episodeJobQuery = useQuery({
    queryKey: ['job', episodeJob?.id],
    queryFn: () => studio.getJob(episodeJob.id),
    enabled: Boolean(episodeJob?.id),
    refetchInterval: (query) => ['done', 'error'].includes(query.state.data?.state) ? false : 1000,
  })
  const analysisQuery = useQuery({
    queryKey: ['job', analysisJob],
    queryFn: () => studio.getJob(analysisJob),
    enabled: Boolean(analysisJob),
    refetchInterval: (query) => ['done', 'error'].includes(query.state.data?.state) ? false : 1000,
  })
  const curveQuery = useQuery({
    queryKey: ['job', curveJob],
    queryFn: () => studio.getJob(curveJob),
    enabled: Boolean(curveJob),
    refetchInterval: (query) => ['done', 'error'].includes(query.state.data?.state) ? false : 1000,
  })

  useEffect(() => {
    if (episodeJobQuery.data?.state === 'done') {
      queryClient.invalidateQueries({ queryKey: ['series', id] })
      navigate(`/series/${id}/episodes/${episodeJob.number}`)
      setEpisodeJob(null)
    }
  }, [episodeJobQuery.data?.state]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (analysisQuery.data?.state === 'done') {
      queryClient.invalidateQueries({ queryKey: ['series', id] })
      setAnalysisJob(null)
    }
  }, [analysisQuery.data?.state, id, queryClient])

  useEffect(() => {
    const state = curveQuery.data?.state
    if (state === 'done') {
      queryClient.invalidateQueries({ queryKey: ['series', id] })
      setCurveJob(null)
    } else if (state === 'error') {
      setCurveError(curveQuery.data?.error || 'Emotional curve generation failed.')
      setCurveJob(null)
    }
  }, [curveQuery.data?.state, curveQuery.data?.error, id, queryClient])

  useEffect(() => {
    if (activeCharacter) {
      setCharacterDraft({ ...activeCharacter })
      setEditingCharacter(false)
    }
  }, [activeCharacter])

  const bp = data?.blueprint || {}
  const genre = bp.genre_data || {}
  const theme = bp.theme_data || {}
  const swot = bp.swot || {}
  const curve = bp.emotional_curve || {}
  const curveBusy = regenerateCurve.isPending || Boolean(curveJob)
  const hasCurve = Boolean(curve.points?.length)
  const episodes = data?.episodes || []
  const characters = data?.characters || []
  const index = data?.index || {}
  const genreTags = (genre.tags || []).slice(0, 4)
  const themeTags = (theme.tags || []).slice(0, 4)
  const themeLabels = themeTags.map((item) =>
    typeof item === 'string' ? { label: item, percentage: 25 } : item,
  )
  const plot = useMemo(() => ({
    main_storyline: bp.main_storyline || '',
    story_world: bp.story_world || bp.setting || '',
    story_beats: bp.story_beats || [],
  }), [bp.main_storyline, bp.story_world, bp.setting, bp.story_beats])

  if (isLoading) return <div className="board-loading"><div className="skeleton" /><div className="skeleton" /></div>
  if (error) return (
    <div className="empty">
      <div>
        <h2>Couldn't open this series.</h2>
        <p className="error">{error.message}</p>
        <button className="button" onClick={() => navigate('/')}>Dashboard</button>
      </div>
    </div>
  )

  function openPlot() {
    setPlotDraft({ ...plot, story_beats: [...plot.story_beats] })
    setEditingStory(false)
    setEditingSetting(false)
    setModal('plot')
  }

  function updateCharacter(key, value) {
    setCharacterDraft((current) => ({ ...current, [key]: value }))
  }

  return (
    <section className="relative min-h-screen bg-black px-4 pb-32 sm:px-6 lg:px-8">

      {/* Top chrome */}
      <div className="absolute top-4 right-4 left-4 z-30 flex items-center justify-between sm:top-5 sm:right-6 sm:left-6 lg:right-8 lg:left-8">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="border-0 bg-transparent cursor-pointer"
        >
          <PocketLogo />
        </button>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 text-sm text-neutral-500 transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.75} />
          All stories
        </button>
      </div>

      <div className="mx-auto max-w-[1400px] pt-16">

        {/* Page title */}
        <div className="mb-6 flex flex-col items-center justify-center text-center">
          <h1 className="flex items-center justify-center gap-3 text-4xl sm:text-5xl md:text-6xl">
            <span className="ideaboard-title-idea text-[1.15em] tracking-[-0.05em] text-white uppercase"><span className="ideaboard-title-one">1</span>DEA</span>
            <span className="ideaboard-title-board text-[1.15em] tracking-[-0.05em] text-[#E61C38] uppercase">B<span className="ideaboard-title-board-o">O</span>ARD</span>
          </h1>
          <p className="mt-2 font-mono text-sm font-bold text-neutral-500">
            {index.title || bp.logline || 'Untitled series'}
          </p>
        </div>

        {/* Two-column bento grid */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_340px]">

          {/* LEFT COLUMN */}
          <div className="flex flex-col gap-4">

            {/* 1. Plot card */}
            <button
              type="button"
              onClick={openPlot}
              className={`${card} flex w-full flex-col p-6 text-left`}
            >
              <CardHeading>Plot and Structure</CardHeading>
              <p className="mt-4 line-clamp-3 text-sm leading-6 text-neutral-400">
                {bp.main_storyline || bp.logline || 'Open the story card to develop the central arc.'}
              </p>
              <span className="mt-3 text-xs font-medium text-[#E61C38] transition-colors">
                Click to read more...
              </span>
            </button>

            {/* 2. Genre + Theme (50/50) */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setModal('genre')}
                className={`${card} flex flex-col p-6 text-left`}
              >
                <CardHeading>Genre</CardHeading>
                <div className="mt-4 flex flex-wrap gap-2">
                  {genreTags.length > 0
                    ? genreTags.map((tag, i) => <Tag key={tag} label={tag} color={TAG_CYCLE[i % TAG_CYCLE.length]} />)
                    : <Tag label={bp.genre || index.genre || 'Unclassified'} />
                  }
                </div>
                <span className="mt-4 text-xs text-neutral-600">Tap to view breakdown →</span>
              </button>

              <button
                type="button"
                onClick={() => setModal('theme')}
                className={`${card} flex flex-col p-6 text-left`}
              >
                <CardHeading>Theme</CardHeading>
                <div className="mt-4 flex flex-wrap gap-2">
                  {themeLabels.length > 0
                    ? themeLabels.map((tag, i) => <Tag key={tag.label} label={tag.label} color={TAG_CYCLE[(i + 2) % TAG_CYCLE.length]} />)
                    : <Tag label={bp.theme || 'Core theme'} />
                  }
                </div>
                <span className="mt-4 text-xs text-neutral-600">Tap to view breakdown →</span>
              </button>
            </div>

            {/* 3. Characters */}
            <div>
              <div className="mb-3 flex items-center justify-between">
                <CardHeading>Characters</CardHeading>
                <span className="text-xs text-neutral-600">{characters.length} voices</span>
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                {characters.map((ch) => (
                  <button
                    key={ch.id || ch.name}
                    type="button"
                    onClick={() => setActiveCharacter(ch)}
                    className="group relative h-48 w-full overflow-hidden rounded-xl border border-neutral-800 bg-neutral-900 transition-all hover:border-[#E61C38]/60 hover:shadow-[0_0_15px_rgba(230,28,56,0.2)]"
                  >
                    {/* Big initials as bg */}
                    <div className="absolute inset-0 flex items-center justify-center text-[5rem] font-bold text-white/[0.05] select-none">
                      {ch.name?.split(/\s+/).map((p) => p[0]).slice(0, 2).join('')}
                    </div>
                    {/* Generated portrait, when it exists — initials stay as the fallback */}
                    {ch.has_image && (
                      <img
                        src={studio.characterImageUrl(id, characterKey(ch))}
                        alt=""
                        loading="lazy"
                        className="absolute inset-0 h-full w-full object-cover"
                      />
                    )}
                    <div className="absolute inset-0 bg-gradient-to-br from-neutral-700 to-black opacity-40 group-hover:opacity-55 transition-opacity" />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/50 to-transparent" />
                    <div className="absolute bottom-0 left-0 flex flex-col p-4 text-left">
                      <p className="text-base font-bold leading-tight text-white">{ch.name}</p>
                      <p className="mt-1 text-[11px] font-medium tracking-wide text-neutral-400 uppercase">
                        {(ch.role || 'Character').split('·')[0].trim()}
                      </p>
                      {ch.voice_id && (
                        <p className="mt-0.5 text-[10px] text-[#E61C38]">{ch.voice_id}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN — Episodes sidebar */}
          <aside className="lg:sticky lg:top-6">
            <div className="rounded-xl border border-neutral-800 bg-[#0D0D0D] overflow-hidden">
              <div className="px-6 pt-6 pb-5 border-b border-neutral-800/70">
                <h2 className="text-[26px] font-semibold text-white tracking-tight">
                  Episodes{' '}
                  <sup className="text-xs text-neutral-500">{episodes.length}</sup>
                </h2>
              </div>
              <div className="divide-y divide-neutral-800/60">
                {episodes.map((ep) => {
                  const isOpen = openEpisode === ep.number
                  const num = String(ep.number).padStart(2, '0')
                  const ready = ep.status === 'ready'
                  return (
                    <div key={ep.number}>
                      {/* Accordion row */}
                      <button
                        type="button"
                        onClick={() => setOpenEpisode(isOpen ? null : ep.number)}
                        className={`group flex w-full items-start gap-5 px-6 py-5 text-left transition-colors hover:bg-neutral-900/60 ${isOpen ? 'bg-neutral-900/50' : ''}`}
                      >
                        <span className="mt-0.5 w-7 shrink-0 text-[15px] font-medium text-neutral-600 tabular-nums select-none">
                          {num}
                        </span>
                        <div className="flex flex-col gap-1 min-w-0">
                          <span className={`text-[16px] font-semibold leading-snug transition-colors ${isOpen ? 'text-[#c084fc]' : 'text-white group-hover:text-[#c084fc]'}`}>
                            {ep.title || `Episode ${ep.number}`}
                          </span>
                          <span className="text-[13px] leading-snug text-neutral-500">
                            {ep.emotional_focus || ep.summary?.slice(0, 80) || 'Story beat'}
                          </span>
                        </div>
                        <ChevronDown
                          className={`mt-1 h-4 w-4 shrink-0 text-neutral-600 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
                          strokeWidth={1.75}
                        />
                      </button>

                      {/* Expandable generate panel — CSS grid rows trick */}
                      <div className={`grid transition-all duration-200 ease-out ${isOpen ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}`}>
                        <div className="overflow-hidden">
                          <div className="mx-5 mb-4 rounded-lg border border-neutral-800 bg-neutral-900/60 px-4 py-3">
                            {ep.summary && (
                              <p className="text-[11px] leading-[1.55] text-neutral-400 mb-2.5">{ep.summary}</p>
                            )}
                            {ep.cliffhanger && (
                              <div className="mb-2.5">
                                <p className="text-[9px] font-bold tracking-widest text-[#E61C38] uppercase mb-1">Cliffhanger</p>
                                <p className="text-[10px] leading-[1.5] text-neutral-500">{ep.cliffhanger}</p>
                              </div>
                            )}
                            <button
                              type="button"
                              onClick={() => ready
                                ? navigate(`/series/${id}/episodes/${ep.number}`)
                                : generation.mutate(ep.number)
                              }
                              disabled={generation.isPending}
                              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-[#E61C38] px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-red-700 active:scale-95 disabled:opacity-45 disabled:cursor-not-allowed"
                            >
                              <Sparkles className="h-3.5 w-3.5" strokeWidth={2} />
                              {ready ? 'Preview Episode' : 'Generate Episode'}
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </aside>
        </div>
      </div>

      {/* Refine bar — floating bottom */}
      <div className="fixed bottom-0 left-0 right-0 z-[90] bg-gradient-to-t from-black via-black to-transparent pt-12 pb-6 px-4 pointer-events-none">
        <div className="mx-auto max-w-[800px] relative flex items-center shadow-[0_0_30px_rgba(230,28,56,0.12)] rounded-full pointer-events-auto">
          <input
            type="text"
            value={refinePrompt}
            onChange={(e) => setRefinePrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && refinePrompt.trim() && refine.mutate()}
            placeholder="Refine the plot, character, or direction…"
            className="w-full bg-[#0A0A0A] border border-neutral-800 rounded-full pl-6 pr-16 py-4 text-[15px] text-white placeholder-neutral-500 focus:outline-none focus:border-red-900/60 transition-colors shadow-inner"
          />
          <button
            type="button"
            onClick={() => refine.mutate()}
            disabled={!refinePrompt.trim() || refine.isPending}
            className="absolute right-2 p-3 bg-[#E61C38] hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-full text-white transition-transform hover:scale-105 active:scale-95 shadow-lg"
          >
            <Sparkles className="w-5 h-5" strokeWidth={2.5} />
          </button>
        </div>
        <p className="text-center text-[9px] text-neutral-700 mt-2">
          Refining can mark generated episodes as needing regeneration.
        </p>
      </div>

      {/* ── Plot modal ── */}
      <Modal open={modal === 'plot'} onClose={() => setModal(null)} size="70vw">
        {plotDraft && (
          <div>
            {/* Story Line header */}
            <div className="flex items-center gap-3 pr-10 mb-5">
              <h3 className="text-2xl font-bold tracking-tight text-white">Story Line</h3>
              <EditIconButton
                label={editingStory ? 'Done editing' : 'Edit story line'}
                editing={editingStory}
                onClick={() => setEditingStory((v) => !v)}
              />
            </div>

            <div className="max-w-3xl">
              {editingStory ? (
                <textarea
                  value={plotDraft.main_storyline}
                  onChange={(e) => setPlotDraft({ ...plotDraft, main_storyline: e.target.value })}
                  rows={3}
                  className="w-full resize-y rounded-lg border border-neutral-700 bg-black/40 px-4 py-3 text-sm leading-7 text-neutral-200 outline-none transition-colors focus:border-[#E61C38]/70"
                />
              ) : (
                <p className="text-sm leading-7 text-neutral-300">{plotDraft.main_storyline}</p>
              )}

              {plotDraft.story_beats.length > 0 && (
                <ul className="mt-5 space-y-3.5">
                  {plotDraft.story_beats.map((beat, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#E61C38]" />
                      {editingStory ? (
                        <textarea
                          value={typeof beat === 'string' ? beat : beat.summary || ''}
                          onChange={(e) =>
                            setPlotDraft({
                              ...plotDraft,
                              story_beats: plotDraft.story_beats.map((b, idx) =>
                                idx === i ? e.target.value : b,
                              ),
                            })
                          }
                          rows={2}
                          className="w-full resize-y rounded-lg border border-neutral-700 bg-black/40 px-3 py-2 text-sm leading-6 text-neutral-300 outline-none transition-colors focus:border-[#E61C38]/70"
                        />
                      ) : (
                        <p className="text-sm leading-6 text-neutral-400">
                          {typeof beat === 'string' ? beat : beat.summary || ''}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Setting */}
            <div className="mt-10 border-t border-neutral-800 pt-8">
              <div className="flex items-center gap-3">
                <h3 className="text-2xl font-bold tracking-tight text-white">Setting</h3>
                <EditIconButton
                  label={editingSetting ? 'Done editing' : 'Edit setting'}
                  editing={editingSetting}
                  onClick={() => setEditingSetting((v) => !v)}
                />
              </div>
              {editingSetting ? (
                <textarea
                  value={plotDraft.story_world}
                  onChange={(e) => setPlotDraft({ ...plotDraft, story_world: e.target.value })}
                  rows={2}
                  className="mt-4 w-full max-w-3xl resize-y rounded-lg border border-neutral-700 bg-black/40 px-4 py-3 text-sm leading-7 text-neutral-200 outline-none transition-colors focus:border-[#E61C38]/70"
                />
              ) : (
                <p className="mt-4 max-w-3xl text-sm leading-7 text-neutral-300">{plotDraft.story_world}</p>
              )}
            </div>

            {/* Save button */}
            {(editingStory || editingSetting) && (
              <div className="mt-6 flex justify-end">
                <button
                  type="button"
                  disabled={saveBlueprint.isPending}
                  onClick={() => {
                    saveBlueprint.mutate({ plot: plotDraft })
                    setEditingStory(false)
                    setEditingSetting(false)
                  }}
                  className="rounded-xl bg-[#E61C38] px-6 py-2.5 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                >
                  Save Changes
                </button>
              </div>
            )}

            {/* SWOT */}
            <div className="mt-10 border-t border-neutral-800 pt-8">
              <div className="flex items-center justify-between mb-5">
                <h4 className="text-xs font-bold tracking-widest text-neutral-500 uppercase">
                  SWOT Analysis · Literature
                </h4>
                {(swot.stale || !swot.strengths) && (
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-neutral-800 px-3 py-1.5 text-xs text-neutral-300 hover:border-neutral-600 transition-colors"
                    onClick={() => regenerateAnalysis.mutate()}
                  >
                    <Sparkles className="h-3 w-3" />
                    Regenerate analysis
                  </button>
                )}
              </div>
              <div className="relative grid max-w-4xl grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-0">
                {/* Crosshair lines */}
                <div className="pointer-events-none absolute inset-0 hidden sm:block">
                  <div className="absolute top-0 bottom-0 left-1/2 w-px -translate-x-1/2 bg-neutral-700" />
                  <div className="absolute right-0 left-0 top-1/2 h-px -translate-y-1/2 bg-neutral-700" />
                </div>
                {QUAD_CONFIG.map((quad) => {
                  const points = swot[quad.key] || ['Analysis will appear after generation.']
                  return (
                    <div key={quad.key} className={`relative ${quad.bg} border ${quad.ring} p-4 sm:border-0 sm:p-5`}>
                      <div className="mb-3 flex items-center gap-2.5">
                        <span className={`flex h-8 w-8 items-center justify-center rounded-md text-sm font-bold ${quad.badge} ${quad.color}`}>
                          {quad.letter}
                        </span>
                        <p className={`text-sm font-bold tracking-wide ${quad.color}`}>{quad.label}</p>
                      </div>
                      <ul className="space-y-2">
                        {points.map((point) => (
                          <li key={point} className="flex items-start gap-2 text-xs leading-5 text-neutral-400">
                            <span className={`mt-1.5 h-1 w-1 shrink-0 rounded-full ${quad.accent}`} />
                            {point}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* ── Genre modal ── */}
      <Modal open={modal === 'genre'} onClose={() => setModal(null)} size="70vw">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex w-full flex-col pt-8 pl-2 lg:w-1/3">
            <h3
              className="font-sans text-7xl font-bold tracking-tight text-white"
              style={{ textShadow: '0 0 10px rgba(230, 28, 56, 0.4)' }}
            >
              <span className="ideaboard-title-board font-normal text-[1.15em] text-[#E61C38] normal-case">G</span>
              <span>enre</span>
            </h3>
            <div className="mt-6 flex flex-wrap gap-2">
              {genreTags.length > 0
                ? genreTags.map((tag, i) => <Tag key={tag} label={tag} color={TAG_CYCLE[i % TAG_CYCLE.length]} />)
                : <Tag label={bp.genre || 'Unclassified'} />}
            </div>
            <p className="mt-6 text-sm leading-6 text-neutral-400">
              {genre.description || 'Genre analysis is generated from the full story blueprint.'}
            </p>
          </div>
          <div className="w-full lg:w-2/3 -mt-8 genre-radar" style={{ minHeight: 400 }}>
            <GenreRadar distribution={genre.distribution} />
          </div>
        </div>
      </Modal>

      {/* ── Theme modal ── */}
      <Modal open={modal === 'theme'} onClose={() => setModal(null)} size="70vw">
        <div className="flex flex-col gap-8 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex w-full flex-col pt-8 pl-2 lg:w-1/3">
            <h3
              className="font-sans text-7xl font-bold tracking-tight text-white"
              style={{ textShadow: '0 0 10px rgba(230, 28, 56, 0.4)' }}
            >
              <span className="ideaboard-title-board font-normal text-[1.15em] text-[#E61C38] normal-case">T</span>
              <span>heme</span>
            </h3>
            <div className="mt-6 flex flex-wrap gap-2">
              {themeLabels.length > 0
                ? themeLabels.map((tag, i) => <Tag key={tag.label} label={tag.label} color={TAG_CYCLE[(i + 2) % TAG_CYCLE.length]} />)
                : <Tag label={bp.theme || 'Core theme'} />}
            </div>
            <p className="mt-6 text-sm leading-6 text-neutral-400">
              {theme.description || 'Theme analysis is generated from the general plot.'}
            </p>
          </div>
          <div className="w-full lg:w-2/3 theme-bars" style={{ borderLeft: '1px solid #222', padding: '30px 20px' }}>
            <ThemeBars themes={themeLabels} />

            {/* Emotional curve — top-3 tracked emotions across the episode plan */}
            <div className="mt-8 border-t border-neutral-800 pt-6">
              <div className="flex items-center justify-between gap-3">
                <p className="text-[11px] font-bold tracking-[0.18em] text-neutral-500 uppercase">
                  Emotional Curve · Full Plot
                </p>
                <button
                  type="button"
                  onClick={() => regenerateCurve.mutate()}
                  disabled={curveBusy}
                  className="inline-flex items-center gap-1.5 text-[10px] font-semibold tracking-wide text-neutral-400 transition-colors hover:text-[#E61C38] disabled:opacity-50"
                >
                  {curveBusy ? (
                    <Loader2 className="h-3 w-3 animate-spin" strokeWidth={2.25} />
                  ) : (
                    <RefreshCw className="h-3 w-3" strokeWidth={2.25} />
                  )}
                  {curveBusy ? 'Charting…' : hasCurve ? 'Regenerate' : 'Generate'}
                </button>
              </div>
              {hasCurve && curve.stale && !curveBusy && (
                <p className="mt-2 text-[11px] text-amber-400">
                  The story changed since this arc was charted — regenerate to refresh it.
                </p>
              )}
              {curveError && (
                <p className="mt-2 text-[11px] text-red-400">{curveError}</p>
              )}
              <div className="mt-3">
                {curveBusy && !hasCurve ? (
                  <div className="flex h-44 w-full items-center justify-center gap-2 text-xs text-neutral-500">
                    <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2} />
                    Charting the emotional arc…
                  </div>
                ) : hasCurve ? (
                  <EmotionalCurveChart
                    idPrefix="theme-plot-curve"
                    emotions={curve.emotions}
                    points={curve.points}
                  />
                ) : (
                  <div className="flex h-44 w-full items-center justify-center text-xs text-neutral-600">
                    No emotional arc charted yet — generate one from the episode plan.
                  </div>
                )}
              </div>
              {hasCurve && curve.summary && (
                <p className="mt-3 text-xs leading-5 text-neutral-500">{curve.summary}</p>
              )}
            </div>
          </div>
        </div>
      </Modal>

      {/* ── Character modal ── */}
      <Modal
        open={Boolean(activeCharacter)}
        onClose={() => setActiveCharacter(null)}
        size="lg"
        tall
        leaveChatBar
      >
        {characterDraft && (
          <div>
            {/* Header */}
            <div className="flex items-center gap-4 mb-6 pr-10">
              <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900 text-neutral-500">
                {characterDraft.has_image ? (
                  <img
                    src={studio.characterImageUrl(id, characterKey(characterDraft))}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <UserRound className="h-9 w-9" strokeWidth={1.5} />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-3">
                  <h3 className="text-xl font-bold tracking-tight text-white">{characterDraft.name}</h3>
                  <EditIconButton
                    label={editingCharacter ? 'Done editing' : 'Edit character'}
                    editing={editingCharacter}
                    onClick={() => setEditingCharacter((v) => !v)}
                  />
                </div>
                <p className="mt-0.5 text-sm text-[#E61C38]">{characterDraft.role}</p>
                <p className="mt-0.5 text-xs text-neutral-500">{characterDraft.gender}</p>
              </div>
            </div>

            {/* Character fields — plain text by default, editable on toggle */}
            <div className="flex flex-col gap-6">
              {[
                ['personality',     'Personality'],
                ['details',         'Details'],
                ['physical_persona','Physical Persona'],
                ['backstory',       'Backstory'],
                ['vocal_direction', 'Vocal direction'],
              ].map(([key, label]) => {
                const value =
                  characterDraft[key] ||
                  characterDraft[
                    key === 'details'         ? 'description'     :
                    key === 'vocal_direction' ? 'vocal_signature' : key
                  ] || ''
                return (
                  <div key={key} className="flex flex-col gap-1.5">
                    <span className="text-xs font-bold tracking-widest text-neutral-500 uppercase">{label}</span>
                    {editingCharacter ? (
                      <textarea
                        value={value}
                        onChange={(e) => updateCharacter(key, e.target.value)}
                        rows={2}
                        className="w-full resize-y bg-transparent px-0 py-0.5 text-sm leading-6 text-neutral-200 outline-none border-0 border-b border-neutral-800 focus:border-[#E61C38]/70 transition-colors"
                      />
                    ) : (
                      <p className="text-sm leading-6 text-neutral-300">
                        {value || 'Not specified yet.'}
                      </p>
                    )}
                  </div>
                )
              })}

              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-bold tracking-widest text-neutral-500 uppercase">Relationships</span>
                {editingCharacter ? (
                  <textarea
                    value={(characterDraft.relationships || []).join('\n')}
                    onChange={(e) => updateCharacter('relationships', e.target.value.split('\n').filter(Boolean))}
                    rows={2}
                    className="w-full resize-y bg-transparent px-0 py-0.5 text-sm leading-6 text-neutral-200 outline-none border-0 border-b border-neutral-800 focus:border-[#E61C38]/70 transition-colors"
                  />
                ) : (
                  <p className="text-sm leading-6 text-neutral-300">
                    {(characterDraft.relationships || []).length
                      ? (characterDraft.relationships || []).join(' · ')
                      : 'None listed yet.'}
                  </p>
                )}
              </div>

              {/* Voice row */}
              <div className="flex items-center justify-between border-t border-neutral-800 pt-5">
                <div>
                  <span className="block text-xs font-bold tracking-widest text-neutral-500 uppercase">Voice</span>
                  <strong className="block mt-1 text-sm font-semibold text-white">
                    {characterDraft.voice_id || 'Not selected'}
                  </strong>
                </div>
                <button
                  type="button"
                  className="rounded-xl border border-neutral-700 px-4 py-2 text-sm text-neutral-300 transition-colors hover:border-neutral-500 hover:text-white"
                  onClick={() => setPicker(true)}
                >
                  Choose voice
                </button>
              </div>

              {editingCharacter && (
                <button
                  type="button"
                  className="self-end inline-flex items-center gap-2 rounded-xl bg-[#E61C38] px-5 py-2.5 text-sm font-bold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
                  disabled={saveCharacter.isPending}
                  onClick={() => saveCharacter.mutate(characterDraft)}
                >
                  Save character
                </button>
              )}
            </div>
          </div>
        )}
      </Modal>

      <VoicePicker
        open={picker}
        selected={activeCharacter?.voice_id}
        onClose={() => setPicker(false)}
        onSelect={(voice) => { chooseVoice.mutate(voice); setPicker(false) }}
      />

      {/* Loading overlays */}
      {episodeJob && <IdeaRefiningLoader />}
      {analysisJob && (
        <div className="fixed inset-0 z-[150]">
          <AILoadingScreen />
          {analysisQuery.data?.state === 'error' && (
            <div className="absolute bottom-8 left-1/2 flex -translate-x-1/2 flex-col items-center gap-3">
              <p className="error text-sm">{analysisQuery.data.error}</p>
              <button className="button ghost" onClick={() => setAnalysisJob(null)}>Dismiss</button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
