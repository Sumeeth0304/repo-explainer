import type { RepoOverview, CodeChunk } from './types'

const BASE = '/api'

export async function checkRepo(repoUrl: string): Promise<RepoOverview | null> {
  const res = await fetch(`${BASE}/repos/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl }),
  })
  if (res.status === 404) return null
  if (!res.ok) return null
  return res.json()
}

export async function ingestRepo(repoUrl: string, githubToken?: string): Promise<RepoOverview> {
  const res = await fetch(`${BASE}/repos/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl, github_token: githubToken || undefined }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Ingest failed')
  }
  return res.json()
}

export async function* streamChat(
  repoId: string,
  question: string,
): AsyncGenerator<string> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_id: repoId, question }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Chat failed')
  }

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    yield decoder.decode(value, { stream: true })
  }
}

export async function fetchSources(repoId: string, question: string): Promise<CodeChunk[]> {
  const res = await fetch(`${BASE}/chat/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_id: repoId, question }),
  })
  if (!res.ok) return []
  const data = await res.json()
  return data.sources ?? []
}
