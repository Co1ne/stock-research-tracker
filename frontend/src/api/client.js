const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

export async function api(path, options = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options
  })
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null ? body.detail : body
    throw new Error(detail || `HTTP ${response.status}`)
  }
  return body
}
