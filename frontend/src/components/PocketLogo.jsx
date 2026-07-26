export default function PocketLogo() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#E61C38] shadow-[0_0_18px_rgba(230,28,56,0.35)]">
        <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden="true">
          <path
            d="M5.5 6.8A3.3 3.3 0 0 1 8.8 3.5h6.4a3.3 3.3 0 0 1 3.3 3.3v7.4a3.3 3.3 0 0 1-3.3 3.3H10l-3.8 3v-3.4a3.3 3.3 0 0 1-.7-2V6.8Z"
            fill="white"
          />
          <path d="m10.5 8 4.5 2.7-4.5 2.8V8Z" fill="#E61C38" />
        </svg>
      </span>
      <span className="text-base font-bold tracking-tight text-white">
        Pocket FM
      </span>
    </div>
  )
}
