import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from '../services/api.js'
import { columnRef, highlight } from '../services/highlight.js'
import { insertBeforeSave, snippetsFor } from '../pages/Workspace.jsx'
import { suggestProgram } from '../state/useWorkspace.js'
import { describeEffect } from '../components/CompilerInspector.jsx'

describe('highlight', () => {
  it('classifies every token shape and preserves the text', () => {
    const src = 'FILTER age >= -18.5; SORT "HOME ADDRESS" desc; @'
    const parts = highlight(src)
    expect(parts.map((p) => p.text).join('')).toBe(src)
    const cls = Object.fromEntries(parts.filter((p) => p.cls !== 'space').map((p) => [p.text, p.cls]))
    expect(cls).toMatchObject({
      FILTER: 'command', age: 'ident', '>=': 'operator', '-18.5': 'number', ';': 'punct',
      '"HOME ADDRESS"': 'string', desc: 'keyword', '@': 'invalid',
    })
  })
})

describe('editor helpers', () => {
  it('quotes column names only when needed', () => {
    expect(columnRef('AGE')).toBe('AGE')
    expect(columnRef('HOME ADDRESS')).toBe('"HOME ADDRESS"')
    expect(columnRef('mode')).toBe('"mode"')
    expect(columnRef('say "hi"')).toBe('"say \\"hi\\""')
    expect(columnRef('2nd')).toBe('"2nd"')
  })

  it('inserts statements above SAVE', () => {
    const src = 'LOAD "a.csv";\nSORT X ASC;\n\nSAVE "b.csv";\n'
    expect(insertBeforeSave(src, 'REMOVE_NULLS;')).toBe('LOAD "a.csv";\nSORT X ASC;\nREMOVE_NULLS;\n\nSAVE "b.csv";\n')
    expect(insertBeforeSave('LOAD "a.csv";', 'REMOVE_NULLS;')).toBe('LOAD "a.csv";\nREMOVE_NULLS;\n')
  })

  it('builds snippets from the real schema', () => {
    const schema = [
      { name: 'NAME', type: 'string' },
      { name: 'MARKS', type: 'integer' },
    ]
    const texts = snippetsFor(schema).map(([, t]) => t)
    expect(texts).toContain('NORMALIZE MARKS;')
    expect(texts).toContain('FILTER NAME == "value";')
    expect(texts).toContain('DROP_COLUMN MARKS;')
    expect(snippetsFor([{ name: 'S', type: 'string' }]).map(([, t]) => t)).not.toContain('NORMALIZE S;')
  })
})

describe('suggestProgram', () => {
  it('turns detected issues into statements', () => {
    const profile = {
      duplicate_rows: 2,
      schema: [
        { name: 'NAME', type: 'string', missing: 0 },
        { name: 'AGE', type: 'integer', missing: 1 },
        { name: 'HOME CITY', type: 'string', missing: 3 },
        { name: 'NOTES', type: 'empty', missing: 5 },
      ],
    }
    expect(suggestProgram('d.csv', profile)).toBe(
      'LOAD "d.csv";\nREMOVE_DUPLICATES;\nDROP_COLUMN NOTES;\nFILL_NULLS AGE USING MEDIAN;\nFILL_NULLS "HOME CITY" USING MODE;\nSAVE "cleaned_d.csv";\n',
    )
  })

  it('is just LOAD and SAVE for a clean file', () => {
    expect(suggestProgram('ok.csv', { duplicate_rows: 0, schema: [{ name: 'A', type: 'integer', missing: 0 }] }))
      .toBe('LOAD "ok.csv";\nSAVE "cleaned_ok.csv";\n')
  })
})

describe('describeEffect', () => {
  it('summarises executor metrics', () => {
    expect(describeEffect({ op: 'fill_nulls', status: 'ok', cells_changed: 1, fill_value: 20 })).toBe('1 cell changed; filled with 20')
    expect(describeEffect({ op: 'filter_rows', status: 'ok', rows_removed: 2 })).toBe('2 rows removed')
    expect(describeEffect({ op: 'normalize', status: 'failed', message: 'boom' })).toBe('boom')
  })
})

describe('api', () => {
  afterEach(() => vi.restoreAllMocks())

  it('maps backend error bodies to ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: { code: 'E_SESSION_NOT_FOUND', message: 'Session not found' } }), { status: 404 },
    )))
    await expect(api.profile('abc')).rejects.toMatchObject({ code: 'E_SESSION_NOT_FOUND', status: 404, message: 'Session not found' })
  })

  it('reports an unreachable backend clearly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await api.health().catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe('E_NETWORK')
  })

  it('sends compile requests with the source as JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'success' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api.compile('s/1', 'LOAD "a.csv";')
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/sessions/s%2F1/compile')
    expect(JSON.parse(opts.body)).toEqual({ source: 'LOAD "a.csv";' })
  })
})
