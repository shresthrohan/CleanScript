const ICON = { error: '✕', warning: '!', info: 'i' }

export default function DiagnosticsPanel({ diagnostics, onJump, emptyText = 'No problems found.' }) {
  if (!diagnostics?.length) return <p className="muted">{emptyText}</p>
  return (
    <ul className="diagnostics">
      {diagnostics.map((d, i) => (
        <li key={i} className={`diag diag-${d.severity}`}>
          <span className="diag-icon" aria-label={d.severity}>{ICON[d.severity]}</span>
          <div className="diag-body">
            <p className="diag-message">{d.message}</p>
            {d.hint && <p className="diag-hint">{d.hint}</p>}
            <p className="diag-meta">
              <code>{d.code}</code>
              <span>{d.stage}</span>
              {d.line && (
                <button type="button" className="link-btn" onClick={() => onJump?.(d.line, d.column)}>
                  Line {d.line}, column {d.column}
                </button>
              )}
            </p>
          </div>
        </li>
      ))}
    </ul>
  )
}
