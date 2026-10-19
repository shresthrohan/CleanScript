import { useState } from 'react'
import { highlight } from '../services/highlight.js'
import { readRecent, SAMPLE } from '../state/useWorkspace.js'

const go = (route) => (window.location.hash = `#/${route}`)

const STAGES = [
  ['Lexer', 'splits the text into tokens'],
  ['Parser', 'checks the grammar and builds a typed AST'],
  ['Semantic analysis', 'checks columns and types against your CSV'],
  ['IR', 'lowers the AST into plain cleaning instructions'],
  ['Code generation', 'writes the equivalent Pandas program'],
  ['Execution', 'runs the instructions on a copy of your data'],
]

export default function Dashboard({ ws }) {
  const [recent] = useState(readRecent)
  const open = async (action) => {
    await action()
    go('workspace')
  }

  return (
    <main className="page dashboard" id="main" tabIndex={-1}>
      <section className="hero">
        <div className="hero-copy">
          <h1>Clean a dataset by writing a program for it.</h1>
          <p className="lede">
            CleanScript is a small language for data cleaning. Each program goes through a real compiler, checked against
            your CSV’s columns, before it touches a single row.
          </p>
          <div className="hero-actions">
            <button type="button" className="btn btn-primary" onClick={() => { ws.reset(); go('workspace') }}>
              New cleaning project
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => open(ws.loadSample)} disabled={Boolean(ws.busy)}>
              Open the students sample
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => open(ws.startDemo)}>
              Replay the recorded demo
            </button>
          </div>
          {ws.error && <p className="field-error" role="alert">{ws.error.message}</p>}
        </div>
        <figure className="hero-program">
          <figcaption>examples/students.clean</figcaption>
          <pre>
            {SAMPLE.program.trimEnd().split('\n').map((line, i) => (
              <div key={i} className="code-line">
                <span className="ln" aria-hidden="true">{i + 1}</span>
                {highlight(line).map((p, j) => <span key={j} className={`tk-${p.cls}`}>{p.text}</span>)}
              </div>
            ))}
          </pre>
        </figure>
      </section>

      <section className="dash-section" aria-labelledby="pipeline-title">
        <h2 id="pipeline-title">What happens when you compile</h2>
        <ol className="stage-list">
          {STAGES.map(([name, what]) => (
            <li key={name}><strong>{name}</strong> {what}</li>
          ))}
        </ol>
      </section>

      <section className="dash-section" aria-labelledby="recent-title">
        <h2 id="recent-title">Recent sessions</h2>
        {recent.length === 0 ? (
          <p className="muted">No sessions yet. Uploaded files are kept on the server for two hours.</p>
        ) : (
          <ul className="recent-list">
            {recent.map((r) => (
              <li key={r.id}>
                <button type="button" className="recent-item" onClick={() => open(() => ws.resume(r.id))}>
                  <span className="recent-name">{r.filename}</span>
                  <span className="muted small">{new Date(r.at).toLocaleString()}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
