import { highlight } from '../services/highlight.js'
import { SAMPLE } from '../state/useWorkspace.js'

function Code({ children }) {
  return (
    <pre className="code-block">
      {children.trim().split('\n').map((line, i) => (
        <div key={i}>{highlight(line).map((p, j) => <span key={j} className={`tk-${p.cls}`}>{p.text}</span>)}</div>
      ))}
    </pre>
  )
}

const COMMANDS = [
  ['LOAD "file.csv";', 'Names the uploaded file. Must be the first statement and match the upload’s name exactly. Not a path.'],
  ['REMOVE_NULLS;', 'Removes every row that has a missing value in any current column.'],
  ['REMOVE_DUPLICATES;', 'Removes rows identical to an earlier row, keeping the first.'],
  ['FILL_NULLS col USING MEAN | MEDIAN;', 'Fills missing values in a numeric column with its mean or median (nulls ignored). Fails if the column has no values.'],
  ['FILL_NULLS col USING MODE;', 'Fills with the most frequent value; on a tie, the one that appears first. Works on any column type.'],
  ['DROP_COLUMN col;', 'Removes a column. You can’t drop the last remaining column.'],
  ['RENAME old TO new;', 'Renames a column. Later statements must use the new name.'],
  ['FILTER col op value;', 'Keeps rows where the comparison is true. Rows with a missing value never match.'],
  ['NORMALIZE col;', 'Min-max scales a numeric column: (x − min) / (max − min). Nulls stay null; a constant column becomes 0.0 with a warning.'],
  ['SORT col ASC | DESC;', 'Stable sort; missing values go last in both directions.'],
  ['SAVE "out.csv";', 'Sets the download name. Must be the last statement; a plain name ending in .csv.'],
]

const GRAMMAR = `program           = load_statement { transform_statement } save_statement EOF ;
load_statement    = "LOAD" STRING ";" ;
save_statement    = "SAVE" STRING ";" ;
transform_statement = remove_nulls | remove_duplicates | fill_nulls | drop_column
                    | rename_column | filter_rows | normalize_column | sort_rows ;
remove_nulls      = "REMOVE_NULLS" ";" ;
remove_duplicates = "REMOVE_DUPLICATES" ";" ;
fill_nulls        = "FILL_NULLS" column_ref "USING" strategy ";" ;
strategy          = "MEAN" | "MEDIAN" | "MODE" ;
drop_column       = "DROP_COLUMN" column_ref ";" ;
rename_column     = "RENAME" column_ref "TO" column_ref ";" ;
filter_rows       = "FILTER" column_ref comparator literal ";" ;
comparator        = "==" | "!=" | ">" | "<" | ">=" | "<=" ;
normalize_column  = "NORMALIZE" column_ref ";" ;
sort_rows         = "SORT" column_ref direction ";" ;
direction         = "ASC" | "DESC" ;
column_ref        = IDENTIFIER | STRING ;
literal           = NUMBER | STRING ;`

const ERRORS = [
  ['E_MISSING_SEMICOLON', 'SORT AGE ASC', 'Every statement ends with ;. The error points just after the last token.'],
  ['E_UNTERMINATED_STRING', 'LOAD "students.csv;', 'Close the string with a double quote on the same line.'],
  ['E_UNKNOWN_COLUMN', 'SORT GRADE ASC;', 'Column names are case-sensitive and must exist at that point. A RENAME or DROP_COLUMN earlier changes what exists.'],
  ['E_TYPE_MISMATCH', 'FILTER AGE >= "18";', 'Compare numeric columns with numbers and text columns with quoted strings. MEAN, MEDIAN and NORMALIZE need numeric columns.'],
  ['E_LOAD_MISMATCH', 'LOAD "other.csv";', 'LOAD must name the file you uploaded.'],
  ['E_SAVE_FILENAME', 'SAVE "../out.csv";', 'Output names can’t contain folders or “..”, and must end in .csv.'],
  ['E_UNKNOWN_COMMAND', 'DROP AGE;', 'Check the spelling. The error suggests the closest command.'],
  ['E_ALL_NULL_COLUMN', 'FILL_NULLS EMPTY USING MEAN;', 'A run-time error: there are no values to compute from. The data stays unchanged.'],
]

const TOC = [
  ['doc-example', 'Example'],
  ['doc-commands', 'Commands'],
  ['doc-rules', 'Names and values'],
  ['doc-grammar', 'Grammar'],
  ['doc-pipeline', 'How compilation works'],
  ['doc-errors', 'Common errors'],
]

export default function Documentation() {
  return (
    <main className="page docs" id="main" tabIndex={-1}>
      <div className="docs-layout">
        <nav className="docs-toc" aria-label="On this page">
          {TOC.map(([id, label]) => (
            // the URL hash is the page router, so in-page links scroll instead of changing it
            <a key={id} href={`#${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView() }}>
              {label}
            </a>
          ))}
        </nav>
        <article className="docs-body">
          <h1>The CleanScript language</h1>
          <p className="lede">
            A program is a list of statements run top to bottom. Each one sees the result of the one before. Your uploaded file is never
            modified. Programs run on a copy.
          </p>

          <h2 id="doc-example">Example</h2>
          <Code>{SAMPLE.program}</Code>
          <p>
            On <code>examples/students.csv</code>, this fills Rohan’s missing age with the median (20) and Kabir’s missing marks with the mean
            (86). It then drops the repeated Aarav row and Meera (age 17), scales marks to 0–1, and sorts highest first. Four rows remain.
          </p>

          <h2 id="doc-commands">Commands</h2>
          <dl className="command-list">
            {COMMANDS.map(([syntax, meaning]) => (
              <div key={syntax}>
                <dt><code>{syntax}</code></dt>
                <dd>{meaning}</dd>
              </div>
            ))}
          </dl>

          <h2 id="doc-rules">Names and values</h2>
          <ul>
            <li>Keywords are case-insensitive (<code>sort</code> works), but column names are matched exactly.</li>
            <li>Bare column names use letters, digits and underscores and don’t start with a digit. Quote anything else: <code>"HOME ADDRESS"</code>.</li>
            <li>Keywords like <code>MODE</code> or <code>TO</code> can’t be bare column names. Quote them: <code>"MODE"</code>.</li>
            <li>Numbers: <code>18</code>, <code>72.5</code>, <code>-3</code>. Strings use double quotes; write <code>\"</code> for a quote and <code>\\</code> for a backslash.</li>
            <li>There are no comments, and no AND/OR in filters. Use two FILTER statements to require both conditions.</li>
            <li>Text comparisons with <code>&lt;</code> or <code>&gt;</code> are alphabetical and case-sensitive.</li>
          </ul>

          <h2 id="doc-grammar">Grammar</h2>
          <p>EBNF. Braces mean “zero or more”; quoted words are keywords; IDENTIFIER, STRING and NUMBER are token types.</p>
          <pre className="code-block">{GRAMMAR}</pre>

          <h2 id="doc-pipeline">How compilation works</h2>
          <ol className="pipeline-explainer">
            <li><strong>Lexer.</strong> Turns text into tokens with line and column numbers, and rejects things like unterminated strings or a lone <code>=</code>.</li>
            <li><strong>Parser.</strong> A recursive-descent parser with one function per grammar rule. It builds a typed AST and stops at the first syntax error.</li>
            <li><strong>Semantic analysis.</strong> Walks the statements with a copy of your CSV’s schema, updating it after RENAME, DROP_COLUMN, FILL_NULLS and NORMALIZE, and reports every error it finds.</li>
            <li><strong>IR.</strong> Lowers the AST into plain JSON instructions such as <code>{'{"op": "fill_nulls", "column": "AGE", "strategy": "MEDIAN"}'}</code>.</li>
            <li><strong>Code generation.</strong> Translates the IR into an equivalent Pandas script you can read and copy.</li>
            <li><strong>Execution.</strong> A restricted interpreter maps each IR operation to one built-in handler. It never runs your text or the generated code as Python.</li>
          </ol>

          <h2 id="doc-errors">Common errors</h2>
          <div className="table-wrap">
            <table className="data-table compact">
              <thead><tr><th>Code</th><th>Example</th><th>What to do</th></tr></thead>
              <tbody>
                {ERRORS.map(([code, example, fix]) => (
                  <tr key={code}><td><code>{code}</code></td><td><code>{example}</code></td><td>{fix}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </main>
  )
}
