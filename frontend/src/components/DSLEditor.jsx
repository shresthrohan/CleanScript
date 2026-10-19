import { useImperativeHandle, useMemo, useRef } from 'react'
import { highlight } from '../services/highlight.js'

// A textarea layered over a highlighted <pre>. Both share font metrics and scroll together.
export default function DSLEditor({ ref, value, onChange, diagnostics = [], readOnly = false, onSubmit }) {
  const textarea = useRef(null)
  const layer = useRef(null)
  const gutter = useRef(null)

  const lineCount = value.split('\n').length
  const marks = useMemo(() => {
    const m = {}
    for (const d of diagnostics) {
      if (!d.line) continue
      const rank = { error: 3, warning: 2, info: 1 }[d.severity]
      if (!m[d.line] || rank > m[d.line].rank) m[d.line] = { rank, severity: d.severity, message: d.message }
    }
    return m
  }, [diagnostics])

  useImperativeHandle(ref, () => ({
    jumpTo(line, column = 1) {
      const el = textarea.current
      if (!el) return
      const lines = value.split('\n')
      let offset = 0
      for (let i = 0; i < line - 1 && i < lines.length; i++) offset += lines[i].length + 1
      offset += Math.max(0, Math.min(column - 1, (lines[line - 1] ?? '').length))
      el.focus()
      el.setSelectionRange(offset, offset)
    },
  }), [value])

  const syncScroll = () => {
    const { scrollTop, scrollLeft } = textarea.current
    layer.current.scrollTop = scrollTop
    layer.current.scrollLeft = scrollLeft
    gutter.current.scrollTop = scrollTop
  }

  return (
    <div className={`editor${readOnly ? ' is-readonly' : ''}`}>
      <div className="editor-gutter" ref={gutter} aria-hidden="true">
        {Array.from({ length: lineCount }, (_, i) => (
          <div key={i} className={`gutter-line${marks[i + 1] ? ` mark-${marks[i + 1].severity}` : ''}`} title={marks[i + 1]?.message}>
            {i + 1}
          </div>
        ))}
      </div>
      <div className="editor-body">
        <pre className="editor-layer" ref={layer} aria-hidden="true">
          {value.split('\n').map((line, i) => (
            <div key={i} className={`code-line${marks[i + 1] ? ` line-${marks[i + 1].severity}` : ''}`}>
              {highlight(line).map((p, j) => (
                <span key={j} className={`tk-${p.cls}`}>{p.text}</span>
              ))}
              {'\n'}
            </div>
          ))}
        </pre>
        <textarea
          ref={textarea}
          className="editor-input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onScroll={syncScroll}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault()
              onSubmit?.()
            }
          }}
          readOnly={readOnly}
          spellCheck={false}
          autoCapitalize="off"
          autoComplete="off"
          wrap="off"
          aria-label="CleanScript program"
          aria-describedby="editor-help"
        />
      </div>
    </div>
  )
}
