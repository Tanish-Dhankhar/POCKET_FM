import { useEffect, useState } from 'react'

export default function TypingText({ lines }) {
  const [line, setLine] = useState(0)
  const [length, setLength] = useState(0)
  const [deleting, setDeleting] = useState(false)
  const text = lines[line % lines.length]

  useEffect(() => {
    const complete = length === text.length
    const empty = length === 0
    const delay = complete && !deleting ? 1300 : deleting ? 24 : 42
    const timer = setTimeout(() => {
      if (complete && !deleting) setDeleting(true)
      else if (empty && deleting) { setDeleting(false); setLine((value) => value + 1) }
      else setLength((value) => value + (deleting ? -1 : 1))
    }, delay)
    return () => clearTimeout(timer)
  }, [length, deleting, text])

  return <div className="building-copy">{text.slice(0, length)}<span className="caret" /></div>
}
