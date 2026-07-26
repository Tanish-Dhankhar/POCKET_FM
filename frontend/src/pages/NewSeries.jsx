import { ArrowLeft, Mic2, PenLine } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const choices = [
  { path: '/new/write', icon: PenLine, label: 'Write' },
  { path: '/new/mic', icon: Mic2, label: 'Speak' },
]

export default function NewSeries() {
  const navigate = useNavigate()
  return (
    <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-black px-6">
      <button
        className="corner-back absolute left-6 top-6"
        onClick={() => navigate('/')}
      >
        <ArrowLeft size={16} /> Dashboard
      </button>

      <p
        className="mb-16 text-sm tracking-wide text-white/30"
        style={{ fontFamily: "'JetBrains Mono', monospace" }}
      >
        I want to start a new story by...
      </p>

      <div className="flex items-end justify-center gap-20 md:gap-32">
        {choices.map(({ path, icon: Icon, label }) => (
          <button
            key={path}
            type="button"
            onClick={() => navigate(path)}
            className="group flex flex-col items-center gap-6 transition-all duration-300 hover:-translate-y-1"
          >
            <span className="flex items-end justify-center text-white/80 transition-colors duration-300 group-hover:text-white">
              <Icon size={64} strokeWidth={1} />
            </span>
            <span className="text-sm font-normal tracking-wide text-white/60 transition-colors duration-300 group-hover:text-white/90">
              {label}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}
