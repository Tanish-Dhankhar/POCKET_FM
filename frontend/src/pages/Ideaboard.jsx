import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as studio from '../api/studio'
import CharacterCard from '../components/CharacterCard'
import EpisodeRow from '../components/EpisodeRow'
import Header from '../components/Header'

const fileFor = {
  logline: 'plot', story_world: 'plot', main_storyline: 'plot',
  theme: 'theme', tone: 'theme',
  genre: 'genre', setting: 'genre', language: 'genre',
}

function StoryCard({ label, field, value, wide, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value || '')
  return <article className={`card story-card ${wide ? 'wide' : ''}`}>
    <div className="row between"><p className="eyebrow">{label}</p><button className="button ghost small" onClick={() => { setDraft(value || ''); setEditing((v) => !v) }}>{editing ? 'Cancel' : 'Edit'}</button></div>
    {editing ? <><textarea className="textarea" rows={wide ? 7 : 3} value={draft} onChange={(e) => setDraft(e.target.value)} /><button className="button primary small" style={{marginTop:10}} onClick={async () => { await onSave(field, draft); setEditing(false) }}>Save</button></> : <p>{value || 'Not specified yet.'}</p>}
  </article>
}

export default function Ideaboard() {
  const { id } = useParams()
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['series', id], queryFn: () => studio.getSeries(id), refetchInterval: 12_000 })
  const editBlueprint = useMutation({ mutationFn: ({ field, value }) => studio.patchBlueprint(id, { [fileFor[field]]: { [field]: value } }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['series', id] }) })
  if (isLoading) return <div className="shell"><Header /><div className="grid"><div className="skeleton" style={{height:260}}/><div className="skeleton" style={{height:260}}/></div></div>
  if (error) return <div className="empty"><div><h2>Couldn’t open this series.</h2><p className="error">{error.message}</p><Link className="button" to="/">Dashboard</Link></div></div>

  const index = data?.index || {}
  const blueprint = data?.blueprint || {}
  const characters = data?.characters || []
  const episodes = data?.episodes || []
  const save = (field, value) => editBlueprint.mutateAsync({ field, value })

  return <div className="shell">
    <Header action={<Link className="button" to="/">All series</Link>} />
    <header className="board-head"><div><p className="eyebrow">Idea board</p><h1 style={{marginBottom:12}}>{index.title || blueprint.logline || 'Untitled series'}</h1><div className="row"><span className="chip">{blueprint.genre || index.genre || 'Story'}</span><span className="chip">{episodes.length} episodes</span></div></div><a className="button ghost" href="#episodes">Episodes ↓</a></header>
    <div className="board-layout">
      <main>
        <section className="section"><div className="section-head"><h2 style={{margin:0}}>The story</h2></div><div className="story-grid">
          <StoryCard label="General plot" field="main_storyline" value={blueprint.main_storyline} wide onSave={save} />
          <StoryCard label="Theme" field="theme" value={blueprint.theme} onSave={save} />
          <StoryCard label="Tone" field="tone" value={blueprint.tone} onSave={save} />
          <StoryCard label="Setting" field="story_world" value={blueprint.story_world || blueprint.setting} wide onSave={save} />
        </div></section>
        <section className="section" id="episodes"><div className="section-head"><div><p className="eyebrow">Season</p><h2 style={{margin:0}}>Episodes</h2></div><span className="muted" style={{fontSize:13}}>Generate one at a time</span></div><div className="episode-list">{episodes.map((episode) => <EpisodeRow key={episode.number} seriesId={id} episode={episode} />)}</div></section>
      </main>
      <aside><section className="section"><div className="section-head"><div><p className="eyebrow">Cast</p><h2 style={{margin:0}}>Characters</h2></div><span className="chip">{characters.length}</span></div><div className="character-list">{characters.map((character) => <CharacterCard key={character.name} seriesId={id} character={character} />)}</div></section></aside>
    </div>
  </div>
}
