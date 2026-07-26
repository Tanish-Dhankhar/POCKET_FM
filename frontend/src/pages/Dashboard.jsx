import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock3, LogOut, MoreHorizontal, Plus, UserCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import * as studio from '../api/studio'
import { relativeTime } from '../lib/format'
import PocketLogo from '../components/PocketLogo'

const CARD_ACCENTS = [
  'from-[#1a0508] via-[#0d0d0d] to-[#0a0a0a]',
  'from-[#0f0a1a] via-[#0d0d0d] to-[#0a0a0a]',
  'from-[#0a1218] via-[#0d0d0d] to-[#0a0a0a]',
  'from-[#1a0f08] via-[#0d0d0d] to-[#0a0a0a]',
]

export default function Dashboard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: series = [], isLoading, error } = useQuery({ queryKey: ['series'], queryFn: studio.listSeries })
  const remove = useMutation({ mutationFn: studio.deleteSeries, onSuccess: () => queryClient.invalidateQueries({ queryKey: ['series'] }) })

  return (
    <>
      {/* Fixed top navbar */}
      <header className="fixed top-0 right-0 left-0 z-40 flex h-16 items-center justify-between border-b border-white/5 bg-black/80 px-4 backdrop-blur sm:px-6">
        <div className="flex select-none items-center gap-3">
          <PocketLogo />
          <span className="h-5 w-px bg-white/20" />
          <h1 className="text-base font-semibold tracking-tight text-white">Dashboard</h1>
        </div>
        <div className="flex items-center gap-1 sm:gap-4">
          <div className="flex items-center gap-2 text-sm text-white/70">
            <UserCircle className="h-5 w-5 text-white/50" strokeWidth={1.5} />
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-white/50 transition-colors hover:text-[#E61C38]"
          >
            <LogOut className="h-4 w-4" strokeWidth={1.7} />
            <span className="hidden sm:inline text-sm">Logout</span>
          </button>
        </div>
      </header>

    <section className="relative min-h-screen overflow-hidden px-5 pt-20 pb-12 sm:px-8 lg:px-16">
      {/* Ambient red glow — top-right */}
      <div
        className="pointer-events-none absolute -right-32 -top-40 h-96 w-96 rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(230,28,56,0.13), transparent 68%)' }}
      />

      <div className="relative mx-auto max-w-7xl">
        {/* Heading */}
        <div className="mb-10 mt-4">
          <p
            className="text-sm font-semibold uppercase tracking-[0.22em] text-[#E61C38]"
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          >
            Creator workspace
          </p>
          <h1 className="mt-3 text-[2.6rem] font-bold leading-tight tracking-tight text-white sm:text-5xl">
            Your stories
          </h1>
          <p
            className="mt-3 max-w-xl text-[13px] leading-6 text-white/45"
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          >
            Continue an existing story or start something new.
          </p>
        </div>

        {error && <p className="notice error">{error.message}</p>}

        {/* Card grid */}
        <motion.div
          className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.045 } } }}
        >
          {isLoading && [1, 2, 3].map((n) => (
            <div key={n} className="skeleton h-[260px] rounded-2xl" />
          ))}

          {series.map((item, index) => (
            <motion.div
              key={item.series_id}
              className="group relative h-[260px] w-full cursor-pointer overflow-hidden rounded-2xl border border-white/[0.08] bg-neutral-900 transition-all duration-300 hover:-translate-y-1 hover:border-[#E61C38]/50 hover:shadow-[0_0_20px_rgba(230,28,56,0.18)]"
              variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
              onClick={() => navigate(`/series/${item.series_id}`)}
            >
              {/* Full-bleed gradient — zooms on hover */}
              <div className={`absolute inset-0 bg-gradient-to-br ${CARD_ACCENTS[index % 4]} transition-transform duration-500 group-hover:scale-105`} />
              {/* Generated cover art, when it exists — the gradient stays as the fallback */}
              {item.has_thumbnail && (
                <img
                  src={studio.thumbnailUrl(item.series_id)}
                  alt=""
                  loading="lazy"
                  className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
              )}
              {/* Readability overlay */}
              <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a] via-[#0a0a0a]/40 to-transparent" />

              {/* Top row */}
              <div className="absolute left-0 right-0 top-0 z-20 flex items-start justify-between p-5">
                <span className="rounded-full border border-white/10 bg-black/40 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/90 backdrop-blur-md">
                  {item.genre || 'SERIES'}
                </span>
                <button
                  type="button"
                  className="rounded-full p-1.5 text-white/60 transition-colors hover:bg-white/20 hover:text-white"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm(`Delete "${item.title || 'this series'}"?`)) remove.mutate(item.series_id)
                  }}
                >
                  <MoreHorizontal className="h-5 w-5" />
                </button>
              </div>

              {/* Bottom content */}
              <div className="absolute bottom-0 left-0 right-0 z-20 flex flex-col p-5 text-left">
                <h2 className="truncate text-xl font-bold leading-tight text-white">
                  {item.title || item.logline || 'Untitled series'}
                </h2>
                <div className="mt-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-white/40">
                  <Clock3 className="h-3.5 w-3.5" strokeWidth={2.5} />
                  <span>{item.updated_at ? relativeTime(item.updated_at) : 'Just now'}</span>
                  <span>·</span>
                  <span>{item.generated_count || 0}/{item.episode_count || item.ep_count || 0} ready</span>
                </div>
              </div>
            </motion.div>
          ))}

          {/* Add new story — last in grid */}
          <motion.button
            type="button"
            className="group flex h-[260px] flex-col items-center justify-center rounded-2xl border border-dashed border-white/15 bg-transparent p-6 text-center transition-all duration-300 hover:-translate-y-1 hover:border-[#E61C38]/50 hover:bg-[#E61C38]/[0.02] hover:shadow-[0_18px_45px_rgba(230,28,56,0.09)]"
            variants={{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }}
            onClick={() => navigate('/new')}
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/15 text-white/50 transition-all duration-300 group-hover:border-[#E61C38]/60 group-hover:bg-[#E61C38]/10 group-hover:text-[#E61C38]">
              <Plus className="h-5 w-5" strokeWidth={1.5} />
            </span>
            <span className="mt-5 text-sm font-semibold text-white/80 group-hover:text-white">
              Add new story
            </span>
            <span className="mt-1.5 text-xs text-white/40">
              Create a fresh project
            </span>
          </motion.button>
        </motion.div>
      </div>
    </section>
    </>
  )
}
