import { useState } from 'react'

export default function CopyButton({ text, label = 'Copy' }) {
  const [state, setState] = useState('idle')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      setState('failed')
    }
    setTimeout(() => setState('idle'), 1600)
  }
  return (
    <button type="button" className="btn btn-ghost btn-small" onClick={copy} aria-live="polite">
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : label}
    </button>
  )
}
