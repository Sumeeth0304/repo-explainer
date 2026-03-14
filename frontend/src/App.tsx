import { useState } from 'react'
import type { RepoOverview } from './types'
import RepoInput from './components/RepoInput'
import OverviewPanel from './components/OverviewPanel'
import Chat from './components/Chat'
import styles from './App.module.css'

export default function App() {
  const [overview, setOverview] = useState<RepoOverview | null>(null)

  if (!overview) {
    return <RepoInput onIngested={setOverview} />
  }

  return (
    <div className={styles.layout}>
      <OverviewPanel overview={overview} onReset={() => setOverview(null)} />
      <Chat repoId={overview.repo_id} />
    </div>
  )
}
