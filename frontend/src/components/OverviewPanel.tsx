import type { RepoOverview } from '../types'
import styles from './OverviewPanel.module.css'

interface Props {
  overview: RepoOverview
  onReset: () => void
}

export default function OverviewPanel({ overview, onReset }: Props) {
  return (
    <aside className={styles.panel}>
      <div className={styles.header}>
        <div>
          <div className={styles.repoName}>{overview.repo_name}</div>
          <div className={styles.stats}>
            <span className={styles.badge}>{overview.files_processed} files</span>
            <span className={styles.badge}>{overview.chunks_stored} chunks</span>
            <span className={`${styles.badge} ${styles.ready}`}>ready</span>
          </div>
        </div>
        <button className={styles.resetBtn} onClick={onReset} title="Analyse another repo">
          ✕
        </button>
      </div>

      <div className={styles.sections}>
        {overview.what_it_does && (
          <Section title="What it does" icon="💡">
            <p>{overview.what_it_does}</p>
          </Section>
        )}

        {overview.tech_stack && overview.tech_stack.length > 0 && (
          <Section title="Tech stack" icon="🧰">
            <div className={styles.tags}>
              {overview.tech_stack.map((t) => (
                <span key={t} className={styles.tag}>{t}</span>
              ))}
            </div>
          </Section>
        )}

        {overview.architecture && (
          <Section title="Architecture" icon="🏗️">
            <p>{overview.architecture}</p>
          </Section>
        )}

        {overview.key_modules && overview.key_modules.length > 0 && (
          <Section title="Key modules" icon="📦">
            <ul className={styles.moduleList}>
              {overview.key_modules.map((m, i) => {
                const [path, ...rest] = m.split('—')
                return (
                  <li key={i} className={styles.moduleItem}>
                    <code className={styles.modulePath}>{path.trim()}</code>
                    {rest.length > 0 && (
                      <span className={styles.moduleDesc}>— {rest.join('—').trim()}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          </Section>
        )}

        {overview.api_flows && (
          <Section title="API flows" icon="🔀">
            <p>{overview.api_flows}</p>
          </Section>
        )}

        {overview.interesting_patterns && (
          <Section title="Patterns & notes" icon="✨">
            <p>{overview.interesting_patterns}</p>
          </Section>
        )}
      </div>
    </aside>
  )
}

function Section({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionTitle}>
        <span>{icon}</span> {title}
      </div>
      <div className={styles.sectionBody}>{children}</div>
    </div>
  )
}
