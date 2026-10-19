const fmt = (n) => (typeof n === 'number' ? n.toLocaleString() : '—')

export default function DatasetStats({ profile }) {
  const columnsWithNulls = profile.schema.filter((c) => c.missing > 0).length
  const stats = [
    ['Rows', fmt(profile.rows)],
    ['Columns', fmt(profile.columns)],
    ['Missing cells', fmt(profile.missing_cells), columnsWithNulls ? `in ${columnsWithNulls} column${columnsWithNulls > 1 ? 's' : ''}` : 'none'],
    ['Duplicate rows', fmt(profile.duplicate_rows), profile.duplicate_rows ? 'exact repeats' : 'none'],
  ]
  return (
    <div>
      <dl className="stats">
        {stats.map(([label, value, note]) => (
          <div className="stat" key={label}>
            <dt>{label}</dt>
            <dd>
              {value}
              {note && <small>{note}</small>}
            </dd>
          </div>
        ))}
      </dl>
      {profile.warnings.length > 0 && (
        <ul className="profile-warnings" aria-label="Detected data-quality issues">
          {profile.warnings.map((w) => (
            <li key={w.code + w.column}>{w.message}</li>
          ))}
        </ul>
      )}
      <p className="muted small">These are detected issues only. Nothing changes until you run a program.</p>
    </div>
  )
}
