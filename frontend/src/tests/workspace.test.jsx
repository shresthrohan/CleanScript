// Workspace behaviour with the API module mocked: Run is gated on a fresh, successful compile.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fixture from '../demo/fixture.json'

vi.mock('../services/api.js', () => ({
  api: {
    health: vi.fn().mockResolvedValue({ status: 'ok' }),
    upload: vi.fn(),
    profile: vi.fn(),
    compile: vi.fn(),
    execute: vi.fn(),
    deleteSession: vi.fn().mockResolvedValue(null),
    downloadUrl: (sid, rid) => `/api/sessions/${sid}/download?result_id=${rid}`,
  },
  ApiError: class extends Error {},
}))

// Node 25's experimental global localStorage shadows jsdom's and is unusable without a file path.
const store = new Map()
vi.stubGlobal('localStorage', {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
})

const { api } = await import('../services/api.js')
const { default: App } = await import('../App.jsx')

const failedReport = {
  ...fixture.compile,
  status: 'failed',
  stages: { lexer: 'passed', parser: 'passed', semantic: 'failed', ir: 'skipped', codegen: 'skipped' },
  ir: null,
  generated_code: null,
  diagnostics: [{ severity: 'error', code: 'E_UNKNOWN_COLUMN', message: "SORT: column 'GRADE' does not exist at this point", stage: 'semantic', line: 2, column: 6, hint: null }],
}

async function openSample() {
  api.upload.mockResolvedValue(fixture.upload)
  window.location.hash = '#/workspace'
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Open the students sample' }))
  return screen.findByLabelText('CleanScript program')
}

describe('Workspace', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('enables Run only after a successful compile of the current source', async () => {
    const editor = await openSample()
    const run = screen.getByRole('button', { name: 'Run' })
    expect(run.disabled).toBe(true)

    api.compile.mockResolvedValue(fixture.compile)
    fireEvent.click(screen.getByRole('button', { name: 'Compile' }))
    await waitFor(() => expect(run.disabled).toBe(false))
    expect(api.compile).toHaveBeenCalledWith(fixture.upload.session_id, editor.value)

    fireEvent.change(editor, { target: { value: editor.value + '\n' } })
    expect(run.disabled).toBe(true)
    expect(screen.getByText('The program changed. Recompile before running.')).toBeTruthy()
  })

  it('shows diagnostics and keeps Run disabled when compilation fails', async () => {
    await openSample()
    api.compile.mockResolvedValue(failedReport)
    fireEvent.click(screen.getByRole('button', { name: 'Compile' }))
    expect(await screen.findAllByText("SORT: column 'GRADE' does not exist at this point")).not.toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Run' }).disabled).toBe(true)
    expect(screen.getAllByRole('button', { name: 'Line 2, column 6' }).length).toBeGreaterThan(0)
  })

  it('runs the compiled program and offers the real download link', async () => {
    await openSample()
    api.compile.mockResolvedValue(fixture.compile)
    api.execute.mockResolvedValue(fixture.execute)
    fireEvent.click(screen.getByRole('button', { name: 'Compile' }))
    const run = screen.getByRole('button', { name: 'Run' })
    await waitFor(() => expect(run.disabled).toBe(false))
    fireEvent.click(run)
    const link = await screen.findByRole('link', { name: /Download cleaned_students.csv/ })
    expect(link.getAttribute('href')).toBe(`/api/sessions/${fixture.upload.session_id}/download?result_id=${fixture.execute.result_id}`)
    expect(api.execute).toHaveBeenCalledWith(fixture.upload.session_id, fixture.compile.compilation_id)
    const cleaned = screen.getByRole('region', { name: 'Cleaned data preview' })
    const names = [...cleaned.querySelectorAll('tbody tr')].map((tr) => tr.children[1].textContent)
    expect(names).toEqual(['Diya', 'Kabir', 'Aarav', 'Rohan'])
  })

  it('labels demo mode and never calls the API to compile', async () => {
    window.location.hash = '#/workspace'
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Replay the recorded demo' }))
    expect(screen.getByText('Demo mode.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Compile' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run' }).disabled).toBe(false))
    expect(api.compile).not.toHaveBeenCalled()
    expect(screen.queryByRole('link', { name: /Download/ })).toBeNull()
  })

  it('shows a friendly message when an upload fails', async () => {
    api.upload.mockRejectedValue(Object.assign(new Error('The CSV file is empty'), { code: 'E_EMPTY_CSV', status: 400 }))
    window.location.hash = '#/workspace'
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Open the students sample' }))
    expect((await screen.findByRole('alert')).textContent).toContain('The CSV file is empty')
  })
})
