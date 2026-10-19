const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

export const STAGES = [
  { id: 'lexer', label: 'Lexer', tab: 'tokens', detail: (r) => r.tokens && plural(r.tokens.length, 'token') },
  { id: 'parser', label: 'Parser', tab: 'ast', detail: (r) => r.ast && plural(r.ast.transforms.length + 2, 'statement') },
  {
    id: 'semantic', label: 'Semantic', tab: 'semantic',
    detail: (r) => {
      const n = (s) => r.diagnostics.filter((d) => d.severity === s && d.stage === 'semantic').length
      return r.semantic && (n('error') ? plural(n('error'), 'error') : n('warning') ? plural(n('warning'), 'warning') : 'schema valid')
    },
  },
  { id: 'ir', label: 'IR', tab: 'ir', detail: (r) => r.ir && plural(r.ir.instructions.length, 'instruction') },
  { id: 'codegen', label: 'Codegen', tab: 'code', detail: (r) => r.generated_code && plural(r.generated_code.trim().split('\n').length, 'line') },
]

const STATUS_LABEL = { passed: 'passed', warning: 'passed with warnings', failed: 'failed', skipped: 'not run', idle: 'not run', stale: 'out of date' }

export default function PipelineVisualizer({ report, execution, stale, activeTab, onSelect }) {
  const execStatus = execution ? (execution.status === 'success' ? (execution.warnings.length ? 'warning' : 'passed') : 'failed') : 'idle'
  const items = [
    ...STAGES.map((s) => ({
      ...s,
      status: !report ? 'idle' : stale ? 'stale' : report.stages[s.id],
      text: report ? s.detail(report) : null,
    })),
    {
      id: 'execute', label: 'Execute', tab: 'logs',
      status: stale && execution ? 'stale' : execStatus,
      text: execution && (execution.status === 'success' ? `${execution.before.rows} → ${execution.after.rows} rows` : 'stopped'),
    },
  ]
  return (
    <ol className="pipeline" aria-label="Compiler pipeline">
      {items.map((s, i) => (
        <li key={s.id} className={`stage stage-${s.status}`}>
          <button
            type="button"
            className="stage-btn"
            aria-pressed={activeTab === s.tab}
            onClick={() => onSelect(s.tab)}
            aria-label={`${s.label}: ${STATUS_LABEL[s.status]}${s.text ? `, ${s.text}` : ''}. Show details.`}
          >
            <span className="stage-index" aria-hidden="true">{i + 1}</span>
            <span className="stage-label">{s.label}</span>
            <span className="stage-detail">{s.text || STATUS_LABEL[s.status]}</span>
          </button>
        </li>
      ))}
    </ol>
  )
}
