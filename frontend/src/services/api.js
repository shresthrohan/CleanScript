// The only module that talks to the backend. Endpoints mirror backend/app/api/routes.py.
const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(message, { code = 'E_HTTP', status = 0 } = {}) {
    super(message)
    this.code = code
    this.status = status
  }
}

const OFFLINE_MESSAGE = 'Can’t reach the CleanScript API. Start the backend (uvicorn app.main:app) and try again.'

function errorFrom(status, body) {
  const err = body?.error
  return new ApiError(err?.message ?? `Request failed with status ${status}`, {
    code: err?.code ?? 'E_HTTP',
    status,
  })
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch {
    throw new ApiError(OFFLINE_MESSAGE, { code: 'E_NETWORK' })
  }
  if (res.status === 204) return null
  const body = await res.json().catch(() => null)
  if (!res.ok) throw errorFrom(res.status, body)
  return body
}

const json = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const sessionPath = (sid) => `/api/sessions/${encodeURIComponent(sid)}`

// XHR instead of fetch so the UI can show real upload progress.
function upload(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/api/sessions/upload`)
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onerror = () => reject(new ApiError(OFFLINE_MESSAGE, { code: 'E_NETWORK' }))
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve(xhr.response) : reject(errorFrom(xhr.status, xhr.response)))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

export const api = {
  health: () => request('/api/health'),
  upload,
  profile: (sid) => request(`${sessionPath(sid)}/profile`),
  compile: (sid, source) => request(`${sessionPath(sid)}/compile`, json({ source })),
  execute: (sid, compilationId) => request(`${sessionPath(sid)}/execute`, json({ compilation_id: compilationId })),
  result: (sid) => request(`${sessionPath(sid)}/result`),
  deleteSession: (sid) => request(sessionPath(sid), { method: 'DELETE' }),
  downloadUrl: (sid, resultId) => `${BASE}${sessionPath(sid)}/download?result_id=${encodeURIComponent(resultId)}`,
}
