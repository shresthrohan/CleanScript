import { useEffect, useState } from 'react'
import Header from './components/Header.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Documentation from './pages/Documentation.jsx'
import Workspace from './pages/Workspace.jsx'
import { useApiStatus, useWorkspace } from './state/useWorkspace.js'

const ROUTES = ['dashboard', 'workspace', 'docs']
const readRoute = () => {
  const r = window.location.hash.replace(/^#\/?/, '')
  return ROUTES.includes(r) ? r : 'dashboard'
}

export default function App() {
  const [route, setRoute] = useState(readRoute)
  const ws = useWorkspace()
  const apiStatus = useApiStatus()

  useEffect(() => {
    const onHash = () => {
      setRoute(readRoute())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  return (
    <>
      <a href="#main" className="skip-link" onClick={(e) => { e.preventDefault(); document.getElementById('main')?.focus() }}>
        Skip to content
      </a>
      <Header route={route} apiStatus={apiStatus} filename={ws.session?.filename} mode={ws.mode} />
      {route === 'dashboard' && <Dashboard ws={ws} />}
      {route === 'workspace' && <Workspace ws={ws} apiStatus={apiStatus} />}
      {route === 'docs' && <Documentation />}
    </>
  )
}
