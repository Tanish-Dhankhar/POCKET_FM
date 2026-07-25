import { Link } from 'react-router-dom'

export default function Header({ action }) {
  return (
    <header className="topbar">
      <Link className="brand" to="/">
        <span className="brand-mark">◒</span>
        <span>Storywave</span>
      </Link>
      {action}
    </header>
  )
}
