// All workspace state and network actions live here; components only render props.
import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../services/api.js'
import { columnRef } from '../services/highlight.js'
import fixture from '../demo/fixture.json'
import sampleCsv from '../../../examples/students.csv?raw'
import sampleProgram from '../../../examples/students.clean?raw'

const RECENT_KEY = 'cleanscript.recent' // only session ids + filenames, never dataset contents

export function readRecent() {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY)) ?? []
  } catch {
    return []
  }
}

function rememberSession(id, filename) {
  const next = [{ id, filename, at: Date.now() }, ...readRecent().filter((r) => r.id !== id)].slice(0, 5)
  localStorage.setItem(RECENT_KEY, JSON.stringify(next))
}

export function forgetSession(id) {
  localStorage.setItem(RECENT_KEY, JSON.stringify(readRecent().filter((r) => r.id !== id)))
}

export const SAMPLE = { csv: sampleCsv, program: sampleProgram, filename: 'students.csv' }

export const starterProgram = (filename) => `LOAD "${filename}";\n\nSAVE "cleaned_${filename}";\n`

// A first program built from the issues the profiler actually detected in this upload,
// so a freshly uploaded CSV compiles into a meaningful cleaning plan straight away.
export function suggestProgram(filename, profile) {
  const lines = []
  if (profile.duplicate_rows > 0) lines.push('REMOVE_DUPLICATES;')
  const empty = profile.schema.filter((c) => c.type === 'empty')
  if (empty.length < profile.schema.length) {
    for (const c of empty) lines.push(`DROP_COLUMN ${columnRef(c.name)};`) // nothing to fill from
  }
  for (const c of profile.schema) {
    if (c.missing === 0 || c.type === 'empty') continue
    const strategy = c.type === 'integer' || c.type === 'float' ? 'MEDIAN' : 'MODE'
    lines.push(`FILL_NULLS ${columnRef(c.name)} USING ${strategy};`)
  }
  return `LOAD "${filename}";\n${lines.map((l) => l + '\n').join('')}SAVE "cleaned_${filename}";\n`
}

export function useWorkspace() {
  const [mode, setMode] = useState('live') // 'live' | 'demo'
  const [session, setSession] = useState(null) // { session_id, filename, profile }
  const [source, setSource] = useState('')
  const [compiled, setCompiled] = useState(null) // { report, source }
  const [execution, setExecution] = useState(null)
  const [busy, setBusy] = useState(null) // 'upload' | 'compile' | 'run' | 'resume' | null
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState(null) // { action, message, code }

  const stale = Boolean(compiled && compiled.source !== source)
  const canCompile = Boolean(session) && !busy && source.trim().length > 0
  const canRun = Boolean(session && compiled?.report.status === 'success' && !stale && !busy)

  const fail = (action, e) => setError({ action, message: e.message, code: e.code })

  const startSession = useCallback((data, program) => {
    setSession(data)
    setCompiled(null)
    setExecution(null)
    setSource(program ?? suggestProgram(data.filename, data.profile))
  }, [])

  const uploadFile = useCallback(async (file, program) => {
    setError(null)
    setBusy('upload')
    setProgress(0)
    try {
      const data = await api.upload(file, setProgress)
      setMode('live')
      startSession(data, program)
      rememberSession(data.session_id, data.filename)
    } catch (e) {
      fail('upload', e)
    } finally {
      setBusy(null)
    }
  }, [startSession])

  const loadSample = useCallback(
    () => uploadFile(new File([SAMPLE.csv], SAMPLE.filename, { type: 'text/csv' }), SAMPLE.program),
    [uploadFile],
  )

  const resume = useCallback(async (id) => {
    setError(null)
    setBusy('resume')
    try {
      const data = await api.profile(id)
      setMode('live')
      startSession(data)
      rememberSession(data.session_id, data.filename)
    } catch (e) {
      if (e.status === 404) forgetSession(id)
      fail('resume', e)
    } finally {
      setBusy(null)
    }
  }, [startSession])

  const compile = useCallback(async () => {
    if (!session) return
    setError(null)
    if (mode === 'demo') {
      setCompiled({ report: fixture.compile, source })
      setExecution(null)
      return
    }
    setBusy('compile')
    const submitted = source
    try {
      const report = await api.compile(session.session_id, submitted)
      setCompiled({ report, source: submitted })
      setExecution(null)
    } catch (e) {
      fail('compile', e)
      if (e.status === 404) setSession(null)
    } finally {
      setBusy(null)
    }
  }, [mode, session, source])

  const run = useCallback(async () => {
    if (!canRun) return
    setError(null)
    if (mode === 'demo') {
      setExecution(fixture.execute)
      return
    }
    setBusy('run')
    try {
      setExecution(await api.execute(session.session_id, compiled.report.compilation_id))
    } catch (e) {
      fail('run', e)
    } finally {
      setBusy(null)
    }
  }, [canRun, mode, session, compiled])

  const reset = useCallback(async () => {
    if (mode === 'live' && session) {
      forgetSession(session.session_id)
      api.deleteSession(session.session_id).catch(() => {}) // best effort; the server also expires sessions
    }
    setMode('live')
    setSession(null)
    setSource('')
    setCompiled(null)
    setExecution(null)
    setError(null)
  }, [mode, session])

  const startDemo = useCallback(() => {
    setError(null)
    setMode('demo')
    setSession(fixture.upload)
    setSource(fixture.source)
    setCompiled(null)
    setExecution(null)
  }, [])

  const downloadUrl = useMemo(
    () => (mode === 'live' && session && execution?.result_id ? api.downloadUrl(session.session_id, execution.result_id) : null),
    [mode, session, execution],
  )

  return {
    mode, session, source, setSource, compiled, execution, busy, progress, error, setError,
    stale, canCompile, canRun, downloadUrl,
    uploadFile, loadSample, resume, compile, run, reset, startDemo,
  }
}

export function useApiStatus() {
  const [status, setStatus] = useState('checking')
  useEffect(() => {
    let alive = true
    const check = () =>
      api.health().then(() => alive && setStatus('online')).catch(() => alive && setStatus('offline'))
    check()
    const id = setInterval(check, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])
  return status
}
