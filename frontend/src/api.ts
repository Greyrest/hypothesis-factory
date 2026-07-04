export const API = import.meta.env.VITE_API_URL || '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API}${path}`, {...init, headers})
  if (!response.ok) {
    const body = await response.json().catch(() => ({detail: response.statusText}))
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))
  }
  return response.json()
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body: unknown) => request<T>(path, {method: 'POST', body: JSON.stringify(body)}),
  put: <T,>(path: string, body: unknown) => request<T>(path, {method: 'PUT', body: JSON.stringify(body)}),
  upload: <T,>(path: string, file: File) => {
    const data = new FormData(); data.append('file', file)
    return request<T>(path, {method: 'POST', body: data})
  },
}

