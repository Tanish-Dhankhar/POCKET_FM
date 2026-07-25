import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, ChevronDown, Pencil, Radio, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as studio from '../api/studio'
import BoardModal from '../components/BoardModal'
import GenerationLoader from '../components/GenerationLoader'
import GenreRadar from '../components/GenreRadar'
import ThemeBars from '../components/ThemeBars'
import VoicePicker from '../components/VoicePicker'
import { characterKey } from '../lib/format'

const jobProgress = {script:12,voices:42,sound:72,mix:88,evaluate:96}
const quadrants = [
  ['strengths','S','Strengths'],['weaknesses','W','Weaknesses'],['opportunities','O','Opportunities'],['threats','T','Threats'],
]

function Tag({children}) { return <span className="board-tag">{children}</span> }

export default function Ideaboard() {
  const {id} = useParams(); const navigate = useNavigate(); const queryClient = useQueryClient()
  const [modal,setModal] = useState(null); const [openEpisode,setOpenEpisode] = useState(1)
  const [activeCharacter,setActiveCharacter] = useState(null); const [picker,setPicker] = useState(false)
  const [characterDraft,setCharacterDraft] = useState(null); const [plotDraft,setPlotDraft] = useState(null)
  const [refinePrompt,setRefinePrompt] = useState(''); const [episodeJob,setEpisodeJob] = useState(null)
  const [analysisJob,setAnalysisJob] = useState(null)
  const {data,isLoading,error} = useQuery({queryKey:['series',id],queryFn:() => studio.getSeries(id),refetchInterval:15000})

  const generation = useMutation({mutationFn:(number) => studio.generateEpisode(id,number,false),onSuccess:(job,number) => setEpisodeJob({id:job.id,number})})
  const refine = useMutation({mutationFn:() => studio.refineSeries(id,refinePrompt),onSuccess:(job) => navigate(`/series/${id}/refining?job=${job.id}`)})
  const saveBlueprint = useMutation({mutationFn:(payload) => studio.patchBlueprint(id,payload),onSuccess:() => {queryClient.invalidateQueries({queryKey:['series',id]});setModal(null)}})
  const saveCharacter = useMutation({mutationFn:(draft) => studio.patchCharacter(id,characterKey(activeCharacter),draft),onSuccess:() => {queryClient.invalidateQueries({queryKey:['series',id]});setActiveCharacter(null)}})
  const chooseVoice = useMutation({mutationFn:(voice) => studio.patchCharacter(id,characterKey(activeCharacter),{voice_id:voice}),onSuccess:() => queryClient.invalidateQueries({queryKey:['series',id]})})
  const regenerateAnalysis = useMutation({mutationFn:() => studio.regenerateAnalysis(id),onSuccess:(job) => setAnalysisJob(job.id)})
  const episodeJobQuery = useQuery({queryKey:['job',episodeJob?.id],queryFn:() => studio.getJob(episodeJob.id),enabled:Boolean(episodeJob?.id),refetchInterval:(query) => ['done','error'].includes(query.state.data?.state) ? false : 1000})
  const analysisQuery = useQuery({queryKey:['job',analysisJob],queryFn:() => studio.getJob(analysisJob),enabled:Boolean(analysisJob),refetchInterval:(query) => ['done','error'].includes(query.state.data?.state) ? false : 1000})

  useEffect(() => { if (episodeJobQuery.data?.state === 'done') { queryClient.invalidateQueries({queryKey:['series',id]}); navigate(`/series/${id}/episodes/${episodeJob.number}`); setEpisodeJob(null) } },[episodeJobQuery.data?.state]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (analysisQuery.data?.state === 'done') { queryClient.invalidateQueries({queryKey:['series',id]}); setAnalysisJob(null) } },[analysisQuery.data?.state,id,queryClient])
  useEffect(() => { if (activeCharacter) setCharacterDraft({...activeCharacter}) },[activeCharacter])

  const bp = data?.blueprint || {}; const genre = bp.genre_data || {}; const theme = bp.theme_data || {}; const swot = bp.swot || {}
  const episodes = data?.episodes || []; const characters = data?.characters || []; const index = data?.index || {}
  const genreTags = (genre.tags || []).slice(0,4); const themeTags = (theme.tags || []).slice(0,4)
  const themeLabels = themeTags.map((item) => typeof item === 'string' ? {label:item,percentage:25} : item)
  const plot = useMemo(() => ({main_storyline:bp.main_storyline || '',story_world:bp.story_world || bp.setting || '',story_beats:bp.story_beats || []}),[bp.main_storyline,bp.story_world,bp.setting,bp.story_beats])

  if (isLoading) return <div className="board-loading"><div className="skeleton"/><div className="skeleton"/></div>
  if (error) return <div className="empty"><div><h2>Couldn’t open this series.</h2><p className="error">{error.message}</p><button className="button" onClick={() => navigate('/')}>Dashboard</button></div></div>

  function openPlot() { setPlotDraft({...plot,story_beats:[...plot.story_beats]}); setModal('plot') }
  function updateCharacter(key,value) { setCharacterDraft((current) => ({...current,[key]:value})) }

  return <section className="ideaboard-screen">
    <header className="board-chrome"><button className="wordmark" onClick={() => navigate('/')}><Radio size={18}/> Storywave</button><button onClick={() => navigate('/')}><ArrowLeft size={15}/> All stories</button></header>
    <div className="board-title"><p>{index.title || bp.logline || 'Untitled series'}</p><h1><span>Idea</span> BOARD</h1></div>
    <div className="ideaboard-layout"><main className="board-main">
      <button className="board-card plot-card" onClick={openPlot}><div><p className="card-label">Plot & Structure</p><h2>{bp.logline || 'Your series storyline'}</h2><p>{bp.main_storyline || 'Open the story card to develop the central arc.'}</p></div><span>Open story line ↗</span></button>
      <div className="classification-grid">
        <button className="board-card classification-card" onClick={() => setModal('genre')}><p className="card-label">Genre</p><h2>{bp.genre || index.genre || 'Unclassified'}</h2><div className="tag-row">{genreTags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div><span>View breakdown →</span></button>
        <button className="board-card classification-card" onClick={() => setModal('theme')}><p className="card-label">Theme</p><h2>{bp.theme || 'Core theme'}</h2><div className="tag-row">{themeLabels.map((tag) => <Tag key={tag.label}>{tag.label}</Tag>)}</div><span>View breakdown →</span></button>
      </div>
      <section className="character-section"><div className="character-section-head"><div><p className="card-label">Cast</p><h2>Characters</h2></div><span>{characters.length} voices</span></div><div className="character-grid">{characters.map((character,index) => <motion.button whileHover={{y:-4}} className="character-tile" key={character.id || character.name} onClick={() => setActiveCharacter(character)}><div className="character-initial">{character.name?.split(/\s+/).map((part) => part[0]).slice(0,2).join('')}</div><div><h3>{character.name}</h3><p>{character.role || 'Character'} · {character.gender || 'Unspecified'}</p><span>{character.voice_id || 'Choose voice'}</span></div></motion.button>)}</div></section>
    </main>
    <aside className="episode-guide"><div className="episode-panel"><div className="episode-panel-head"><h2>Episodes <sup>{episodes.length}</sup></h2></div><div className="episode-stack">{episodes.map((episode) => { const open = openEpisode === episode.number; const ready = episode.status === 'ready'; return <article className={`episode-item ${open ? 'open' : ''}`} key={episode.number}><button className="episode-item-head" onClick={() => setOpenEpisode(open ? null : episode.number)}><div><h3>E{episode.number}. {episode.title || `Episode ${episode.number}`}</h3><p>{episode.emotional_focus || 'Story beat'} · {index.ep_minutes || 10}M</p></div><ChevronDown size={17}/></button><AnimatePresence initial={false}>{open && <motion.div className="episode-expanded" initial={{height:0,opacity:0}} animate={{height:'auto',opacity:1}} exit={{height:0,opacity:0}}><div><p>{episode.summary}</p>{episode.cliffhanger && <p className="cliffhanger"><strong>Cliffhanger</strong>{episode.cliffhanger}</p>}<button className="episode-action" disabled={generation.isPending} onClick={() => ready ? navigate(`/series/${id}/episodes/${episode.number}`) : generation.mutate(episode.number)}><Sparkles size={14}/>{ready ? 'Preview episode' : 'Generate episode'}</button></div></motion.div>}</AnimatePresence></article>})}</div></div></aside></div>

    <div className="refine-bar"><div><Sparkles size={17}/><input value={refinePrompt} onChange={(e) => setRefinePrompt(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && refinePrompt.trim() && refine.mutate()} placeholder="Refine the plot, character, or direction…"/><button disabled={!refinePrompt.trim() || refine.isPending} onClick={() => refine.mutate()}>Refine</button></div><small>Refining can mark generated episodes as needing regeneration.</small></div>

    <BoardModal open={modal === 'plot'} onClose={() => setModal(null)} wide><div className="modal-heading"><p className="eyebrow">Plot & Structure</p><h2>Story Line</h2></div>{plotDraft && <div className="plot-editor"><label>Main storyline<textarea value={plotDraft.main_storyline} onChange={(e) => setPlotDraft({...plotDraft,main_storyline:e.target.value})}/></label><label>Setting<textarea value={plotDraft.story_world} onChange={(e) => setPlotDraft({...plotDraft,story_world:e.target.value})}/></label><div><p className="card-label">Story beats</p>{plotDraft.story_beats.map((beat,index) => <textarea key={index} value={typeof beat === 'string' ? beat : beat.summary || ''} onChange={(e) => setPlotDraft({...plotDraft,story_beats:plotDraft.story_beats.map((item,i) => i === index ? e.target.value : item)})}/>)}</div><button className="button primary" onClick={() => saveBlueprint.mutate({plot:plotDraft})}>Save story</button></div>}<div className="swot-section"><div className="swot-head"><p className="card-label">SWOT Analysis · Literature</p>{(swot.stale || !swot.strengths) && <button className="button small" onClick={() => regenerateAnalysis.mutate()}><Sparkles size={13}/> Regenerate analysis</button>}</div><div className="swot-grid">{quadrants.map(([key,letter,label]) => <div className={`swot-quadrant ${key}`} key={key}><div><b>{letter}</b><strong>{label}</strong></div><ul>{(swot[key] || ['Analysis will appear after generation.']).map((point) => <li key={point}>{point}</li>)}</ul></div>)}</div></div></BoardModal>

    <BoardModal open={modal === 'genre'} onClose={() => setModal(null)} wide><div className="breakdown-modal"><div><h2><span>G</span>enre</h2><div className="tag-row">{genreTags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div><p>{genre.description || 'Genre analysis is generated from the full story blueprint.'}</p></div><GenreRadar distribution={genre.distribution}/></div></BoardModal>
    <BoardModal open={modal === 'theme'} onClose={() => setModal(null)} wide><div className="breakdown-modal theme-breakdown"><div><h2><span>T</span>heme</h2><div className="tag-row">{themeLabels.map((tag) => <Tag key={tag.label}>{tag.label}</Tag>)}</div><p>{theme.description || 'Theme analysis is generated from the general plot.'}</p></div><ThemeBars themes={themeLabels}/></div></BoardModal>

    <BoardModal open={Boolean(activeCharacter)} onClose={() => setActiveCharacter(null)}>{characterDraft && <div className="character-modal"><div className="character-modal-head"><div className="character-avatar"><UserRound/></div><div><h2>{characterDraft.name}</h2><p>{characterDraft.role} · {characterDraft.gender}</p></div></div>{[['personality','Personality'],['details','Details'],['physical_persona','Physical Persona'],['backstory','Backstory'],['vocal_direction','Vocal direction']].map(([key,label]) => <label key={key}><span>{label}</span><textarea value={characterDraft[key] || characterDraft[key === 'details' ? 'description' : key === 'vocal_direction' ? 'vocal_signature' : key] || ''} onChange={(e) => updateCharacter(key,e.target.value)}/></label>)}<label><span>Relationships</span><textarea value={(characterDraft.relationships || []).join('\n')} onChange={(e) => updateCharacter('relationships',e.target.value.split('\n').filter(Boolean))}/></label><div className="voice-control"><div><span>Voice</span><strong>{activeCharacter.voice_id || 'Not selected'}</strong></div><button className="button" onClick={() => setPicker(true)}>Choose voice</button></div><button className="button primary character-save" onClick={() => saveCharacter.mutate(characterDraft)}><Pencil size={14}/> Save character</button></div>}</BoardModal>
    <VoicePicker open={picker} selected={activeCharacter?.voice_id} onClose={() => setPicker(false)} onSelect={(voice) => {chooseVoice.mutate(voice);setPicker(false)}}/>
    {episodeJob && <GenerationLoader mode="episode" message={episodeJobQuery.data?.message || 'Preparing episode generation…'} progress={jobProgress[episodeJobQuery.data?.step] || 7} error={episodeJobQuery.data?.state === 'error' ? episodeJobQuery.data.error : generation.error?.message} onBack={() => setEpisodeJob(null)}/>} 
    {analysisJob && <GenerationLoader mode="refine" message={analysisQuery.data?.message || 'Analysing the story…'} progress={analysisQuery.data?.state === 'done' ? 100 : 55} error={analysisQuery.data?.state === 'error' ? analysisQuery.data.error : null} onBack={() => setAnalysisJob(null)}/>} 
  </section>
}
