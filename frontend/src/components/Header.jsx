const ROUTES = [
  ['dashboard', 'Projects'],
  ['workspace', 'Workspace'],
  ['docs', 'Language guide'],
]

const STATUS_TEXT = { checking: 'Checking API…', online: 'API connected', offline: 'API offline' }

export default function Header({ route, apiStatus, filename, mode }) {
  return (
    <header className="header">
      <a className="brand" href="#/dashboard" aria-label="CleanScript home">
        <span className="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="22" height="22">
            <path d="M9 11l5 5-5 5M16 22h7" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <span className="brand-name">CleanScript</span>
      </a>
      <nav className="nav" aria-label="Main">
        {ROUTES.map(([id, label]) => (
          <a key={id} href={`#/${id}`} className="nav-link" aria-current={route === id ? 'page' : undefined}>
            {label}
          </a>
        ))}
      </nav>
      <div className="header-meta">
        {filename && (
          <span className="header-file" title={filename}>
            {mode === 'demo' && <span className="demo-pill">Demo</span>}
            {filename}
          </span>
        )}
        <span className={`api-status api-${apiStatus}`} role="status">
          <span className="dot" aria-hidden="true" />
          {STATUS_TEXT[apiStatus]}
        </span>
      </div>
    </header>
  )
}
