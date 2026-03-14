import { useState } from 'react'
import { checkRepo, ingestRepo } from '../api'
import type { RepoOverview } from '../types'
import styles from './RepoInput.module.css'

interface Props {
  onIngested: (overview: RepoOverview) => void
}

export default function RepoInput({ onIngested }: Props) {
  const [url, setUrl] = useState('')
  const [token, setToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState('')

  const STAGES = [
    'Cloning file tree…',
    'Chunking source files…',
    'Embedding with OpenAI…',
    'Storing in Pinecone…',
    'Analysing with Claude…',
  ]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!url.trim()) return
    setLoading(true)
    setError(null)

    // Cycle through fake progress stages while the real call runs
    let stageIdx = 0
    setStage(STAGES[0])
    const interval = setInterval(() => {
      stageIdx = (stageIdx + 1) % STAGES.length
      setStage(STAGES[stageIdx])
    }, 2500)

    try {
      // Check if already ingested — skip re-ingestion if so
      const existing = await checkRepo(url.trim())
      if (existing) {
        onIngested(existing)
        return
      }
      const overview = await ingestRepo(url.trim(), token.trim() || undefined)
      onIngested(overview)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
    } finally {
      clearInterval(interval)
      setLoading(false)
      setStage('')
    }
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.hero}>
        <div className={styles.logo}>
          <span className={styles.logoIcon}>⬡</span>
          <span className={styles.logoText}>RepoMind</span>
        </div>
        <h1 className={styles.headline}>Understand any codebase instantly</h1>
        <p className={styles.sub}>
          Paste a GitHub repo URL. RepoMind indexes it and lets you ask questions
          like "How does auth work?" or "Where is the payment logic?"
        </p>
      </div>

      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.inputRow}>
          <input
            className={styles.input}
            type="text"
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading}
            autoFocus
          />
          <button className={styles.btn} type="submit" disabled={loading || !url.trim()}>
            {loading ? <span className={styles.spinner} /> : 'Analyse'}
          </button>
        </div>

        <button
          type="button"
          className={styles.tokenToggle}
          onClick={() => setShowToken((v) => !v)}
        >
          {showToken ? '▾' : '▸'} GitHub token (optional — for private repos)
        </button>

        {showToken && (
          <input
            className={styles.input}
            type="password"
            placeholder="ghp_..."
            value={token}
            onChange={(e) => setToken(e.target.value)}
            disabled={loading}
          />
        )}

        {loading && (
          <div className={styles.progress}>
            <div className={styles.progressBar}>
              <div className={styles.progressFill} />
            </div>
            <span className={styles.stage}>{stage}</span>
          </div>
        )}

        {error && <div className={styles.error}>{error}</div>}
      </form>

      <div className={styles.examples}>
        <span className={styles.examplesLabel}>Try:</span>
        {[
          'facebook/react',
          'tiangolo/fastapi',
          'vercel/next.js',
        ].map((ex) => (
          <button
            key={ex}
            className={styles.exampleBtn}
            onClick={() => setUrl(`https://github.com/${ex}`)}
            disabled={loading}
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}
