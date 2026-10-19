import { useState } from 'react'
import DataTable from './DataTable.jsx'

function Delta({ label, before, after }) {
  const diff = after - before
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd>
        {before.toLocaleString()} <span className="arrow" aria-label="to">→</span> {after.toLocaleString()}
        <small className={diff < 0 ? 'down' : diff > 0 ? 'up' : undefined}>
          {diff === 0 ? 'unchanged' : `${diff > 0 ? '+' : '−'}${Math.abs(diff).toLocaleString()}`}
        </small>
      </dd>
    </div>
  )
}

export default function ResultsPanel({ execution, beforeProfile, downloadUrl, mode, stale }) {
  const [view, setView] = useState('after')

  if (!execution) {
    return (
      <section className="panel results" aria-labelledby="results-title">
        <div className="panel-head"><h2 id="results-title">Results</h2></div>
        <p className="muted">Compile, then run the program to clean a copy of the dataset. Results and the download appear here.</p>
      </section>
    )
  }
  if (execution.status === 'failed') {
    return (
      <section className="panel results" aria-labelledby="results-title">
        <div className="panel-head"><h2 id="results-title">Results</h2></div>
        <div className="alert alert-error" role="alert">
          <strong>The program stopped while running.</strong> {execution.error.message}
          {execution.error.source && ` (line ${execution.error.source.line})`}. Nothing was saved, and the uploaded data is unchanged.
        </div>
      </section>
    )
  }

  const after = execution.result_profile
  return (
    <section className="panel results" aria-labelledby="results-title">
      <div className="panel-head">
        <h2 id="results-title">Results</h2>
        {stale && <span className="badge badge-warning">From an earlier version of the program</span>}
        <div className="panel-actions">
          {downloadUrl ? (
            <a className="btn btn-primary" href={downloadUrl} download={execution.output_filename}>
              Download {execution.output_filename}
            </a>
          ) : (
            <span className="muted small">{mode === 'demo' ? 'Downloads need a live session.' : ''}</span>
          )}
        </div>
      </div>

      <dl className="stats">
        <Delta label="Rows" before={beforeProfile.rows} after={after.rows} />
        <Delta label="Columns" before={beforeProfile.columns} after={after.columns} />
        <Delta label="Missing cells" before={beforeProfile.missing_cells} after={after.missing_cells} />
        <Delta label="Duplicate rows" before={beforeProfile.duplicate_rows} after={after.duplicate_rows} />
      </dl>

      {execution.warnings.length > 0 && (
        <ul className="profile-warnings" aria-label="Execution warnings">
          {execution.warnings.map((w, i) => <li key={i}>Line {w.source?.line}: {w.message}</li>)}
        </ul>
      )}

      <div className="segmented" role="group" aria-label="Preview">
        <button type="button" aria-pressed={view === 'after'} onClick={() => setView('after')}>Cleaned data</button>
        <button type="button" aria-pressed={view === 'before'} onClick={() => setView('before')}>Original data</button>
      </div>
      {view === 'after' ? (
        <DataTable preview={after.preview} schema={after.schema} caption="Cleaned data preview" />
      ) : (
        <DataTable preview={beforeProfile.preview} schema={beforeProfile.schema} caption="Original data preview" />
      )}
    </section>
  )
}
