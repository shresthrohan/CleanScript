// Float columns keep a decimal point (JSON turns 1.0 into 1) so the preview reads like the CSV.
const fmtCell = (v, type) => {
  if (typeof v !== 'number') return String(v)
  if (Number.isInteger(v)) return type === 'float' ? v.toFixed(1) : String(v)
  return Number(v.toFixed(6)).toString()
}

const statsTitle = (col) =>
  col.stats
    ? `min ${col.stats.min} · max ${col.stats.max} · mean ${Number(col.stats.mean.toFixed(4))} · median ${col.stats.median}`
    : `${col.unique} distinct values`

export default function DataTable({ preview, schema, caption }) {
  if (!preview) return null
  const byName = Object.fromEntries((schema ?? []).map((c) => [c.name, c]))
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table className="data-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col" className="row-num">#</th>
            {preview.columns.map((name) => {
              const col = byName[name]
              return (
                <th scope="col" key={name} title={col ? statsTitle(col) : name}>
                  <span className="col-name">{name}</span>
                  {col && (
                    <span className="col-meta">
                      <span className={`type type-${col.type}`}>{col.type}</span>
                      {col.missing > 0 && <span className="missing">{col.missing} missing</span>}
                    </span>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {preview.rows.length === 0 && (
            <tr>
              <td colSpan={preview.columns.length + 1} className="empty-cell">No rows</td>
            </tr>
          )}
          {preview.rows.map((row, i) => (
            <tr key={i}>
              <td className="row-num">{i + 1}</td>
              {row.map((v, j) =>
                v === null ? (
                  <td key={j} className="null-cell" aria-label="missing value">null</td>
                ) : (
                  <td key={j} className={typeof v === 'number' ? 'num' : undefined} title={String(v).length > 40 ? String(v) : undefined}>
                    {fmtCell(v, byName[preview.columns[j]]?.type)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {preview.truncated && (
        <p className="table-note">Showing the first {preview.rows.length} of {preview.total_rows.toLocaleString()} rows.</p>
      )}
    </div>
  )
}
