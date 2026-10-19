import { useRef, useState } from 'react'
import CompilerInspector from '../components/CompilerInspector.jsx'
import DataTable from '../components/DataTable.jsx'
import DatasetStats from '../components/DatasetStats.jsx'
import DiagnosticsPanel from '../components/DiagnosticsPanel.jsx'
import DSLEditor from '../components/DSLEditor.jsx'
import FileUploader from '../components/FileUploader.jsx'
import PipelineVisualizer from '../components/PipelineVisualizer.jsx'
import ResultsPanel from '../components/ResultsPanel.jsx'
import CopyButton from '../components/CopyButton.jsx'
import { columnRef } from '../services/highlight.js'
import { SAMPLE, starterProgram, suggestProgram } from '../state/useWorkspace.js'

export function snippetsFor(schema) {
  const numeric = schema.find((c) => c.type === 'integer' || c.type === 'float')
  const text = schema.find((c) => c.type === 'string')
  const first = schema[0]
  const last = schema[schema.length - 1]
  const out = [
    ['Remove rows with missing values', 'REMOVE_NULLS;'],
    ['Remove duplicate rows', 'REMOVE_DUPLICATES;'],
  ]
  if (numeric) out.push(['Fill missing numbers with the median', `FILL_NULLS ${columnRef(numeric.name)} USING MEDIAN;`])
  if (first) out.push(['Fill missing values with the mode', `FILL_NULLS ${columnRef((text ?? first).name)} USING MODE;`])
  if (numeric) out.push(['Keep rows by a number', `FILTER ${columnRef(numeric.name)} >= 0;`])
  if (text) out.push(['Keep rows by a text value', `FILTER ${columnRef(text.name)} == "value";`])
  if (numeric) out.push(['Scale a column to 0–1', `NORMALIZE ${columnRef(numeric.name)};`])
  if (first) out.push(['Sort rows', `SORT ${columnRef(first.name)} ASC;`])
  if (first) out.push(['Rename a column', `RENAME ${columnRef(first.name)} TO NEW_NAME;`])
  if (schema.length > 1) out.push(['Drop a column', `DROP_COLUMN ${columnRef(last.name)};`])
  return out
}

// Insert a statement on the line above SAVE (or at the end if there is no SAVE yet).
export function insertBeforeSave(source, statement) {
  const lines = source.split('\n')
  const saveAt = lines.findLastIndex((l) => /^\s*SAVE\b/i.test(l))
  if (saveAt === -1) return `${source.replace(/\n*$/, '\n')}${statement}\n`
  let at = saveAt
  while (at > 0 && lines[at - 1].trim() === '') at--
  lines.splice(at, 0, statement)
  return lines.join('\n')
}

function EmptyWorkspace({ ws, apiStatus }) {
  return (
    <div className="empty-workspace">
      <h1>Start with a dataset</h1>
      <p className="lede">Upload a CSV to profile it, then write a CleanScript program against its columns.</p>
      <FileUploader onFile={ws.uploadFile} busy={ws.busy === 'upload'} progress={ws.progress} />
      <div className="empty-actions">
        <button type="button" className="btn btn-secondary" onClick={ws.loadSample} disabled={Boolean(ws.busy)}>
          Open the students sample
        </button>
        <button type="button" className="btn btn-ghost" onClick={ws.startDemo}>
          Replay the recorded demo
        </button>
      </div>
      {apiStatus === 'offline' && (
        <p className="muted small">The API is offline. Start the backend to upload files, or replay the recorded demo, which works without it.</p>
      )}
    </div>
  )
}

export default function Workspace({ ws, apiStatus }) {
  const editor = useRef(null)
  const [tab, setTab] = useState('tokens')
  const report = ws.compiled?.report
  const errorsShown = report?.diagnostics ?? []
  const jump = (line, column) => editor.current?.jumpTo(line, column)

  const errorBanner = ws.error && (
    <div className="alert alert-error" role="alert">
      <span>{ws.error.message}</span>
      <button type="button" className="link-btn" onClick={() => ws.setError(null)}>Dismiss</button>
    </div>
  )

  if (!ws.session) {
    return (
      <main className="page" id="main" tabIndex={-1}>
        {errorBanner}
        <EmptyWorkspace ws={ws} apiStatus={apiStatus} />
      </main>
    )
  }

  const { profile, filename } = ws.session
  const demo = ws.mode === 'demo'
  const compileLabel = ws.busy === 'compile' ? 'Compiling…' : ws.stale ? 'Recompile' : 'Compile'
  const runHint = !report
    ? 'Compile first to enable Run.'
    : report.status !== 'success'
      ? 'Fix the errors and recompile to enable Run.'
      : ws.stale
        ? 'The program changed. Recompile before running.'
        : 'Ready to run on a copy of the data.'

  const compileAndFocus = async () => {
    await ws.compile()
    setTab((t) => (t === 'logs' ? 'tokens' : t))
  }
  const runAndShow = async () => {
    await ws.run()
    setTab('logs')
  }

  return (
    <main className="page workspace" id="main" tabIndex={-1}>
      {demo && (
        <div className="demo-banner" role="note">
          <strong>Demo mode.</strong> You’re viewing a recorded run of the students sample, replayed from a saved backend response. Nothing here
          is compiled live. <button type="button" className="link-btn" onClick={ws.reset}>Leave demo</button>
        </div>
      )}
      {errorBanner}

      <div className="workspace-grid">
        <section className="panel dataset" aria-labelledby="dataset-title">
          <div className="panel-head">
            <h2 id="dataset-title">Dataset</h2>
            <span className="file-chip" title={filename}>{filename}</span>
            {!demo && (
              <div className="panel-actions">
                <FileUploader onFile={ws.uploadFile} busy={ws.busy === 'upload'} progress={ws.progress} compact />
              </div>
            )}
          </div>
          <DatasetStats profile={profile} />
          <DataTable preview={profile.preview} schema={profile.schema} caption={`Preview of ${filename}`} />
        </section>

        <section className="panel program" aria-labelledby="program-title">
          <div className="panel-head">
            <h2 id="program-title">Program</h2>
            <div className="panel-actions">
              {!demo && (
                <select
                  className="select"
                  aria-label="Insert a statement"
                  value=""
                  onChange={(e) => e.target.value && ws.setSource(insertBeforeSave(ws.source, e.target.value))}
                >
                  <option value="">Insert statement…</option>
                  {snippetsFor(profile.schema).map(([label, text]) => (
                    <option key={label} value={text}>{label}</option>
                  ))}
                </select>
              )}
              {!demo && filename === SAMPLE.filename && (
                <button type="button" className="btn btn-ghost btn-small" onClick={() => ws.setSource(SAMPLE.program)}>
                  Load sample program
                </button>
              )}
              {!demo && (
                <button type="button" className="btn btn-ghost btn-small" onClick={() => ws.setSource(suggestProgram(filename, profile))}
                  title="A program that fixes the duplicates and missing values detected in this file">
                  Suggest from issues
                </button>
              )}
              {!demo && (
                <button type="button" className="btn btn-ghost btn-small" onClick={() => ws.setSource(starterProgram(filename))}>
                  Clear
                </button>
              )}
              <CopyButton text={ws.source} />
            </div>
          </div>
          <DSLEditor ref={editor} value={ws.source} onChange={ws.setSource} diagnostics={ws.stale ? [] : errorsShown} readOnly={demo} onSubmit={compileAndFocus} />
          <p id="editor-help" className="muted small">
            One statement per line, each ending in a semicolon. Ctrl+Enter compiles. <a href="#/docs">Language guide</a>
          </p>
          <div className="toolbar">
            <button type="button" className="btn btn-primary" onClick={compileAndFocus} disabled={!ws.canCompile}>
              {compileLabel}
            </button>
            <button type="button" className="btn btn-run" onClick={runAndShow} disabled={!ws.canRun} aria-describedby="run-hint">
              {ws.busy === 'run' ? 'Running…' : 'Run'}
            </button>
            <span id="run-hint" className={`run-hint${report?.status === 'success' && !ws.stale ? ' is-ready' : ''}`}>{runHint}</span>
            <button type="button" className="btn btn-ghost btn-small push-right" onClick={ws.reset}>
              {demo ? 'Leave demo' : 'Close project'}
            </button>
          </div>
          {report && !ws.stale && report.diagnostics.length > 0 && (
            <div className="editor-diagnostics">
              <DiagnosticsPanel diagnostics={report.diagnostics} onJump={jump} />
            </div>
          )}
        </section>
      </div>

      <PipelineVisualizer report={report} execution={ws.execution} stale={ws.stale} activeTab={tab} onSelect={setTab} />

      <div className="workspace-lower">
        <CompilerInspector report={report} execution={ws.execution} stale={ws.stale} tab={tab} setTab={setTab} onJump={jump} />
        <ResultsPanel execution={ws.execution} beforeProfile={profile} downloadUrl={ws.downloadUrl} mode={ws.mode} stale={ws.stale} />
      </div>
    </main>
  )
}
