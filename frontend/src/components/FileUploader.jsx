import { useRef, useState } from 'react'

export default function FileUploader({ onFile, busy, progress, compact = false }) {
  const input = useRef(null)
  const [dragging, setDragging] = useState(false)
  const [localError, setLocalError] = useState(null)

  const accept = (file) => {
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setLocalError(`“${file.name}” isn’t a .csv file. Choose a comma-separated file.`)
      return
    }
    setLocalError(null)
    onFile(file)
  }

  return (
    <div
      className={`uploader${dragging ? ' is-dragging' : ''}${compact ? ' is-compact' : ''}`}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        accept(e.dataTransfer.files?.[0])
      }}
    >
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="visually-hidden"
        id="csv-input"
        onChange={(e) => {
          accept(e.target.files?.[0])
          e.target.value = ''
        }}
      />
      {busy ? (
        <div className="upload-progress" role="status">
          <span>Uploading and profiling… {Math.round(progress * 100)}%</span>
          <progress max="1" value={progress} aria-label="Upload progress" />
        </div>
      ) : (
        <>
          <button type="button" className="btn btn-secondary" onClick={() => input.current?.click()}>
            {compact ? 'Replace CSV' : 'Choose a CSV file'}
          </button>
          {!compact && <p className="muted">or drop it here. UTF-8, up to 5 MB.</p>}
        </>
      )}
      {localError && <p className="field-error" role="alert">{localError}</p>}
    </div>
  )
}
