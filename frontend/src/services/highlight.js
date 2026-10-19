// Display-only syntax colouring for the editor. Compilation always happens on the backend;
// this scanner just mirrors the lexer's token shapes closely enough to colour them.
export const COMMANDS = [
  'LOAD', 'SAVE', 'REMOVE_NULLS', 'REMOVE_DUPLICATES', 'FILL_NULLS', 'DROP_COLUMN',
  'RENAME', 'FILTER', 'NORMALIZE', 'SORT',
]
const SECONDARY = ['USING', 'TO', 'MEAN', 'MEDIAN', 'MODE', 'ASC', 'DESC']
const RESERVED = new Set([...COMMANDS, ...SECONDARY])

// A column name as CleanScript source: bare when it's a legal identifier, quoted otherwise.
export const columnRef = (name) =>
  /^[A-Za-z_][A-Za-z0-9_]*$/.test(name) && !RESERVED.has(name.toUpperCase())
    ? name
    : `"${name.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`

const RULES = [
  ['space', /\s+/y],
  ['string', /"(?:[^"\\\n]|\\.)*"?/y],
  ['number', /-?\d+(?:\.\d+)?/y],
  ['word', /[A-Za-z_][A-Za-z0-9_]*/y],
  ['operator', /==|!=|>=|<=|>|</y],
  ['punct', /;/y],
  ['invalid', /./y],
]

export function highlight(source) {
  const parts = []
  let pos = 0
  while (pos < source.length) {
    for (const [kind, re] of RULES) {
      re.lastIndex = pos
      const m = re.exec(source)
      if (!m) continue
      let cls = kind
      if (kind === 'word') {
        const upper = m[0].toUpperCase()
        cls = COMMANDS.includes(upper) ? 'command' : SECONDARY.includes(upper) ? 'keyword' : 'ident'
      }
      parts.push({ text: m[0], cls })
      pos += m[0].length
      break
    }
  }
  return parts
}
