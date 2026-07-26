import { Link } from 'react-router-dom'
import PocketLogo from './PocketLogo'

export default function Header({ action }) {
  return (
    <header className="topbar">
      <Link className="brand" to="/">
        <PocketLogo />
      </Link>
      {action}
    </header>
  )
}
