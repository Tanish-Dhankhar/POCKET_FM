import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'

const RAW_TEXT =
  "kind of chaotic, like nobody really knows what's going on so can you check in with them and see where things landed, honestly it's all a bit of a mess right now and · "
const RAW_STREAM = RAW_TEXT.repeat(4)

const STRUCTURED_TEXT =
  "I'll check if the notes from yesterday's meeting were sent out, or if they're still pending review · "
const STRUCTURED_STREAM = STRUCTURED_TEXT.repeat(4)

const PHRASES = [
  'Synthesizing the voices...',
  'Injecting plot twists...',
  'Re-aligning the themes...',
  'Calibrating dramatic tension...',
  'Scoring the scene...',
  'Reconstructing the fog...',
]

const PILL_BARS = Array.from({ length: 9 }, (_, i) => ({
  dur: 0.55 + ((i * 13 + 3) % 7) * 0.07,
  delay: ((i * 5 + 2) % 8) * 0.06,
  min: 0.28 + ((i * 11 + 4) % 5) * 0.1,
  white: i % 3 === 0,
}))

const RAW_PATH =
  'M -80 70 C 0 -10 120 10 115 110 C 111 178 15 172 45 98 ' +
  'C 72 42 188 76 274 150 C 338 205 416 182 500 164'

const OUT_PATH =
  'M 500 168 C 640 214 780 210 884 168 C 968 134 1012 104 1080 78'

function Typewriter({ phrases }) {
  const [idx, setIdx] = useState(0)
  const [sub, setSub] = useState(0)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    const current = phrases[idx]

    if (!deleting && sub === current.length) {
      const t = setTimeout(() => setDeleting(true), 800)
      return () => clearTimeout(t)
    }
    if (deleting && sub === 0) {
      setDeleting(false)
      setIdx((i) => (i + 1) % phrases.length)
      return
    }
    const t = setTimeout(
      () => setSub((s) => s + (deleting ? -1 : 1)),
      deleting ? 15 : 32,
    )
    return () => clearTimeout(t)
  }, [sub, deleting, idx, phrases])

  return (
    <span className="whitespace-nowrap text-lg font-bold text-white sm:text-xl">
      {phrases[idx].slice(0, sub)}
      <motion.span
        className="ml-0.5 inline-block text-[#E61C38]"
        animate={{ opacity: [1, 0] }}
        transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse' }}
      >
        |
      </motion.span>
    </span>
  )
}

export default function IdeaRefiningLoader() {
  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden bg-black">

      {/* Header */}
      <div className="mb-14 flex items-center gap-2.5">
        <motion.span
          className="inline-block h-1.5 w-1.5 rounded-full bg-[#E61C38]"
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
        />
        <span className="text-xs font-bold tracking-[0.3em] text-neutral-500 uppercase">
          Generating your episode
        </span>
      </div>

      {/* Stage */}
      <div className="relative h-[320px] w-full max-w-6xl">

        <svg
          viewBox="0 0 1000 320"
          className="absolute inset-0 h-full w-full"
          fill="none"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <path id="rawCurve" d={RAW_PATH} />
            <path id="outCurve" d={OUT_PATH} />
          </defs>

          {/* Faint guide stroke under the raw ribbon */}
          <use href="#rawCurve" stroke="#141414" strokeWidth="1.25" />
          {/* Bright solid red band the structured output rides on */}
          <use href="#outCurve" stroke="#FF1F3D" strokeWidth="30" strokeLinecap="round" />

          {/* LEFT — raw input: muted, mono */}
          <text fill="#6b6b6b" fontSize="14" fontFamily="'JetBrains Mono', monospace" letterSpacing="0.5">
            <textPath href="#rawCurve" startOffset="0">
              {RAW_STREAM}
              <animate attributeName="startOffset" from="-520" to="0" dur="9s" repeatCount="indefinite" />
            </textPath>
          </text>

          {/* RIGHT — structured output: bold white */}
          <text fill="#ffffff" fontSize="16" fontWeight="700" fontFamily="'DM Sans', sans-serif" letterSpacing="0.2">
            <textPath href="#outCurve" startOffset="0">
              {STRUCTURED_STREAM}
              <animate attributeName="startOffset" from="-520" to="0" dur="8s" repeatCount="indefinite" />
            </textPath>
          </text>
        </svg>

        {/* Center audio processor pill */}
        <div className="absolute top-1/2 left-1/2 z-20 -translate-x-1/2 -translate-y-1/2">
          <div className="flex h-12 items-center gap-[3px] rounded-full border border-neutral-700 bg-[#0A0A0A] px-5">
            {PILL_BARS.map((b, i) => (
              <motion.span
                key={i}
                className={`w-[3px] rounded-full ${b.white ? 'bg-white' : 'bg-[#E61C38]'}`}
                style={{ height: 26, transformOrigin: 'center' }}
                animate={{ scaleY: [1, b.min, b.min + 0.5, b.min, 1] }}
                transition={{
                  duration: b.dur,
                  ease: 'easeInOut',
                  repeat: Infinity,
                  delay: b.delay,
                }}
              />
            ))}
          </div>
        </div>

        {/* Edge fades */}
        <div className="pointer-events-none absolute inset-y-0 left-0 w-32 bg-gradient-to-r from-black to-transparent" />
        <div className="pointer-events-none absolute inset-y-0 right-0 w-32 bg-gradient-to-l from-black to-transparent" />
      </div>

      {/* Typewriter phrase */}
      <div className="mt-10 flex h-8 items-center justify-center text-center">
        <Typewriter phrases={PHRASES} />
      </div>

    </div>
  )
}
