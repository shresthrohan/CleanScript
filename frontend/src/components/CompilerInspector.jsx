import { useRef } from 'react'
import CopyButton from './CopyButton.jsx'
import DiagnosticsPanel from './DiagnosticsPanel.jsx'

export const TABS = [
  ['tokens', 'Tokens'],
  ['ast', 'AST'],
  ['semantic', 'Semantic analysis'],
  ['ir', 'IR'],
  ['code', 'Generated code'],
  ['logs', 'Execution log'],
]

const NOT_REACHED = {
  tokens: 'The lexer stopped on an error, so there are no tokens.',
  ast: 'The parser didn’t run or found a syntax error, so there is no AST.',
  semantic: 'Semantic analysis runs after the program parses.',
  ir: 'IR is generated only for programs with no errors.',
  code: 'Code is generated only from valid IR.',
}

function Tokens({ tokens }) {
  return (
    <div className="table-wrap">
      <table className="data-table compact">
        <thead>
          <tr><th>#</th><th>Kind</th><th>Lexeme</th><th>Value</th><th>Position</th></tr>
        </thead>
        <tbody>
          {tokens.map((t, i) => (
            <tr key={i}>
              <td className="row-num">{i}</td>
              <td><span className={`tok-kind tok-${t.category.toLowerCase()}`}>{t.type}</span></td>
              <td><code>{t.lexeme || '∅'}</code></td>
              <td><code>{t.value === null ? '' : JSON.stringify(t.value)}</code></td>
              <td className="num">{t.line}:{t.column}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const isNode = (v) => v && typeof v === 'object' && !Array.isArray(v) && 'node' in v

function AstNode({ value, name }) {
  if (Array.isArray(value)) {
    return (
      <li>
        <details open>
          <summary><span className="ast-field">{name}</span> <span className="muted">[{value.length}]</span></summary>
          <ul>{value.map((v, i) => <AstNode key={i} value={v} name={String(i)} />)}</ul>
        </details>
      </li>
    )
  }
  if (isNode(value)) {
    const { node, span, ...rest } = value
    const scalars = Object.entries(rest).filter(([, v]) => !isNode(v) && !Array.isArray(v))
    const children = Object.entries(rest).filter(([, v]) => isNode(v) || Array.isArray(v))
    return (
      <li>
        <details open>
          <summary>
            {name && <span className="ast-field">{name}: </span>}
            <span className="ast-node">{node}</span>
            {scalars.map(([k, v]) => (
              <span key={k} className="ast-attr"> {k}=<code>{JSON.stringify(v)}</code></span>
            ))}
            {span && <span className="ast-span"> {span.line}:{span.column}</span>}
          </summary>
          {children.length > 0 && <ul>{children.map(([k, v]) => <AstNode key={k} value={v} name={k} />)}</ul>}
        </details>
      </li>
    )
  }
  return <li><span className="ast-field">{name}</span> <code>{JSON.stringify(value)}</code></li>
}

function Semantic({ report, onJump }) {
  const diags = report.diagnostics.filter((d) => d.stage === 'semantic')
  return (
    <div className="stack">
      <DiagnosticsPanel diagnostics={diags} onJump={onJump} emptyText="Every column reference, type and file name checked out." />
      <h4>Schema after each statement</h4>
      <p className="muted small">The analyzer tracks the columns each statement will see, so later checks use renamed or dropped columns correctly.</p>
      <div className="table-wrap">
        <table className="data-table compact">
          <thead><tr><th>Line</th><th>Statement</th><th>Check</th><th>Columns afterwards</th></tr></thead>
          <tbody>
            {report.semantic.trace.map((t, i) => (
              <tr key={i}>
                <td className="num">{t.line}</td>
                <td><code>{t.statement}</code></td>
                <td><span className={`check check-${t.status ?? 'ok'}`}>{t.status ?? 'ok'}</span></td>
                <td className="schema-cell">
                  {t.schema.map((c) => (
                    <span key={c.name} className="schema-chip" title={c.has_nulls ? 'may contain nulls' : 'no nulls'}>
                      {c.name}<small>{c.type}{c.has_nulls ? ' · nulls' : ''}</small>
                    </span>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Ir({ ir }) {
  return (
    <div className="stack">
      <p className="muted small">
        Input <code>{ir.input}</code>, output <code>{ir.output}</code>, IR version {ir.version}. The executor runs exactly these instructions.
      </p>
      <ol className="ir-list">
        {ir.instructions.map((ins) => {
          const { index, op, source, ...args } = ins
          return (
            <li key={index}>
              <code className="ir-op">{op}</code>
              {Object.entries(args).map(([k, v]) => (
                <span key={k} className="ir-arg">{k}=<code>{JSON.stringify(v)}</code></span>
              ))}
              <span className="ast-span">line {source.line}</span>
            </li>
          )
        })}
      </ol>
      <details>
        <summary>Raw IR JSON</summary>
        <div className="code-head"><CopyButton text={JSON.stringify(ir, null, 2)} label="Copy JSON" /></div>
        <pre className="code-block">{JSON.stringify(ir, null, 2)}</pre>
      </details>
    </div>
  )
}

function Code({ code }) {
  return (
    <div className="stack">
      <div className="code-head">
        <p className="muted small">Equivalent Pandas program, for inspection. CleanScript runs the IR through its restricted interpreter instead of executing this code.</p>
        <CopyButton text={code} label="Copy code" />
      </div>
      <pre className="code-block numbered">
        {code.replace(/\n$/, '').split('\n').map((line, i) => (
          <span key={i} className={line.trimStart().startsWith('#') ? 'py-comment' : undefined}>{line}{'\n'}</span>
        ))}
      </pre>
    </div>
  )
}

function Logs({ execution }) {
  if (!execution) return <p className="muted">Run the compiled program to see per-operation results.</p>
  return (
    <div className="stack">
      {execution.error && (
        <div className="alert alert-error" role="alert">
          <strong>Execution stopped at instruction {execution.error.index + 1}</strong>
          {execution.error.source && ` (line ${execution.error.source.line})`}: {execution.error.message}. The uploaded data is unchanged.
        </div>
      )}
      <div className="table-wrap">
        <table className="data-table compact">
          <thead>
            <tr><th>#</th><th>Operation</th><th>Line</th><th>Rows</th><th>Columns</th><th>Effect</th><th>Time</th></tr>
          </thead>
          <tbody>
            {execution.operations.map((o) => (
              <tr key={o.index} className={o.status === 'failed' ? 'row-failed' : undefined}>
                <td className="row-num">{o.index + 1}</td>
                <td><code>{o.op}</code></td>
                <td className="num">{o.source?.line}</td>
                <td className="num">{o.rows_before}{o.rows_after !== undefined && ` → ${o.rows_after}`}</td>
                <td className="num">{o.columns_before}{o.columns_after !== undefined && ` → ${o.columns_after}`}</td>
                <td>{describeEffect(o)}</td>
                <td className="num">{o.duration_ms !== undefined ? `${o.duration_ms} ms` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {execution.warnings.length > 0 && (
        <ul className="profile-warnings">
          {execution.warnings.map((w, i) => <li key={i}>Line {w.source?.line}: {w.message}</li>)}
        </ul>
      )}
    </div>
  )
}

export function describeEffect(o) {
  if (o.status === 'failed') return o.message
  const parts = []
  if (o.rows_removed !== undefined) parts.push(`${o.rows_removed} row${o.rows_removed === 1 ? '' : 's'} removed`)
  if (o.cells_changed !== undefined) parts.push(`${o.cells_changed} cell${o.cells_changed === 1 ? '' : 's'} changed`)
  if (o.fill_value !== undefined) parts.push(`filled with ${JSON.stringify(o.fill_value)}`)
  if (o.min !== undefined) parts.push(`min ${o.min}, max ${o.max}`)
  if (o.order_changed !== undefined) parts.push(o.order_changed ? 'rows reordered' : 'order unchanged')
  if (o.op === 'drop_column') parts.push('column dropped')
  if (o.op === 'rename_column') parts.push('column renamed')
  return parts.join('; ') || '—'
}

export default function CompilerInspector({ report, execution, stale, tab, setTab, onJump }) {
  const tabRefs = useRef({})
  const onKeyDown = (e) => {
    const i = TABS.findIndex(([id]) => id === tab)
    const next = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : null
    if (next === null) return
    const id = TABS[(next + TABS.length) % TABS.length][0]
    setTab(id)
    tabRefs.current[id]?.focus()
  }

  let body
  if (!report && tab !== 'logs') body = <p className="muted">Compile the program to see each stage’s output here.</p>
  else if (tab === 'tokens') body = report.tokens ? <Tokens tokens={report.tokens} /> : <DiagnosticsPanel diagnostics={report.diagnostics} onJump={onJump} emptyText={NOT_REACHED.tokens} />
  else if (tab === 'ast') body = report.ast ? <ul className="ast-tree"><AstNode value={report.ast} /></ul> : <p className="muted">{NOT_REACHED.ast}</p>
  else if (tab === 'semantic') body = report.semantic ? <Semantic report={report} onJump={onJump} /> : <p className="muted">{NOT_REACHED.semantic}</p>
  else if (tab === 'ir') body = report.ir ? <Ir ir={report.ir} /> : <p className="muted">{NOT_REACHED.ir}</p>
  else if (tab === 'code') body = report.generated_code ? <Code code={report.generated_code} /> : <p className="muted">{NOT_REACHED.code}</p>
  else body = <Logs execution={execution} />

  return (
    <section className="panel inspector" aria-labelledby="inspector-title">
      <div className="panel-head">
        <h2 id="inspector-title">Compiler output</h2>
        {stale && <span className="badge badge-warning">Source changed since this compile</span>}
      </div>
      <div className="tabs" role="tablist" aria-label="Compiler stages" onKeyDown={onKeyDown}>
        {TABS.map(([id, label]) => (
          <button
            key={id}
            ref={(el) => (tabRefs.current[id] = el)}
            role="tab"
            id={`tab-${id}`}
            aria-selected={tab === id}
            aria-controls="inspector-panel"
            tabIndex={tab === id ? 0 : -1}
            className="tab"
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel" id="inspector-panel" aria-labelledby={`tab-${tab}`}>
        {body}
      </div>
    </section>
  )
}
