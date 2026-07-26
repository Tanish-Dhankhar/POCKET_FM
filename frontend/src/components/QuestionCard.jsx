import { AnimatePresence, motion } from 'framer-motion'
import { Check, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'

export default function QuestionCard({ question, index, total, value, onChange, onNext, onBack, busy }) {
  const recommended = question?.options?.find((o) => o.recommended)?.label || question?.options?.[0]?.label || ''
  const [custom, setCustom] = useState('')
  useEffect(() => setCustom(''), [index])
  const selected = value || recommended

  return (
    <motion.div
      className="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-neutral-800 bg-[#0A0A0A]"
      initial={{ y: 24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 12, opacity: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
    >
      {/* Red progress bar flush at top */}
      <div className="h-0.5 w-full bg-neutral-900">
        <motion.div
          className="h-full bg-[#E61C38]"
          animate={{ width: `${((index + 1) / total) * 100}%` }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        />
      </div>

      <div className="p-8">
        {/* Counter */}
        <div className="mb-6">
          <span
            className="text-xs font-bold uppercase tracking-[0.25em] text-neutral-600"
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          >
            Question {index + 1} / {total}
          </span>
        </div>

        {/* Question text — slides on index change */}
        <AnimatePresence mode="wait">
          <motion.h2
            key={index}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="mb-6 text-xl font-bold leading-snug text-white"
          >
            {question?.question}
          </motion.h2>
        </AnimatePresence>

        {/* Option list */}
        <div className="mb-5 flex flex-col gap-2.5">
          {(question?.options || []).map((option) => (
            <button
              key={option.label}
              type="button"
              onClick={() => { setCustom(''); onChange(option.label) }}
              className={`flex items-start justify-between gap-4 rounded-xl border px-4 py-3.5 text-left transition-colors ${
                selected === option.label
                  ? 'border-[#E61C38]/60 bg-[#E61C38]/[0.08]'
                  : 'border-neutral-800 bg-neutral-950 hover:border-neutral-700'
              }`}
            >
              <span>
                <strong className="block text-sm text-white">{option.label}</strong>
                {option.detail && (
                  <p className="mt-1 text-xs leading-relaxed text-neutral-500">{option.detail}</p>
                )}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {option.recommended && (
                  <em className="text-[10px] not-italic text-neutral-500">Recommended</em>
                )}
                {selected === option.label && (
                  <Check className="h-4 w-4 text-[#E61C38]" strokeWidth={2} />
                )}
              </span>
            </button>
          ))}
        </div>

        {/* Custom answer input */}
        <input
          className="w-full rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-3 text-sm text-white placeholder-neutral-600 outline-none transition-colors focus:border-neutral-700"
          value={custom}
          placeholder="Or write your own answer…"
          onChange={(e) => { setCustom(e.target.value); onChange(e.target.value || recommended) }}
        />

        {/* Actions */}
        <div className="mt-5 flex items-center justify-between">
          <button
            type="button"
            onClick={onBack}
            disabled={busy}
            className="text-xs font-medium text-neutral-600 transition-colors hover:text-neutral-400 disabled:opacity-40"
          >
            Back
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={!selected || busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#E61C38] px-5 py-2 text-xs font-bold text-white transition-colors hover:bg-red-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-30"
          >
            {busy ? 'Thinking…' : index === total - 1 ? 'Review story' : 'Next'}
            <ChevronRight className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        </div>
      </div>
    </motion.div>
  )
}
