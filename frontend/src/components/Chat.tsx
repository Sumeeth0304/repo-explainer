import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { streamChat, fetchSources } from '../api'
import type { ChatMessage, CodeChunk } from '../types'
import styles from './Chat.module.css'

const SUGGESTIONS = [
  'What does this project do?',
  'How does authentication work?',
  'Where is the database schema defined?',
  'What are the main API endpoints?',
  'How is routing handled?',
  'Where is the payment / billing logic?',
]

interface Props {
  repoId: string
}

export default function Chat({ repoId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [expandedSources, setExpandedSources] = useState<number | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function sendMessage(question: string) {
    if (!question.trim() || streaming) return
    setInput('')
    setStreaming(true)

    const userMsg: ChatMessage = { role: 'user', content: question }
    setMessages((prev) => [...prev, userMsg])

    // Fetch sources in parallel while streaming starts
    const sourcesPromise = fetchSources(repoId, question)

    const assistantMsg: ChatMessage = { role: 'assistant', content: '' }
    setMessages((prev) => [...prev, assistantMsg])

    try {
      for await (const chunk of streamChat(repoId, question)) {
        setMessages((prev) => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: updated[updated.length - 1].content + chunk,
          }
          return updated
        })
      }

      const sources = await sourcesPromise
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { ...updated[updated.length - 1], sources }
        return updated
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error contacting API'
      setMessages((prev) => {
        const updated = [...prev]
        updated[updated.length - 1] = { ...updated[updated.length - 1], content: `⚠️ ${msg}` }
        return updated
      })
    } finally {
      setStreaming(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className={styles.chat}>
      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>⬡</div>
            <p className={styles.emptyTitle}>Ask anything about this repo</p>
            <div className={styles.suggestions}>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className={styles.suggestionBtn}
                  onClick={() => sendMessage(s)}
                  disabled={streaming}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`${styles.message} ${styles[msg.role]}`}>
            <div className={styles.avatar}>{msg.role === 'user' ? '👤' : '⬡'}</div>
            <div className={styles.bubble}>
              {msg.role === 'user' ? (
                <p>{msg.content}</p>
              ) : (
                <div className={styles.markdown}>
                  <ReactMarkdown
                    components={{
                      code({ className, children, ...rest }) {
                        const match = /language-(\w+)/.exec(className || '')
                        const isBlock = !rest.ref && String(children).includes('\n')
                        return isBlock && match ? (
                          <SyntaxHighlighter
                            style={oneDark as Record<string, React.CSSProperties>}
                            language={match[1]}
                            PreTag="div"
                          >
                            {String(children).replace(/\n$/, '')}
                          </SyntaxHighlighter>
                        ) : (
                          <code className={styles.inlineCode} {...rest}>
                            {children}
                          </code>
                        )
                      },
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                  {msg.content === '' && <span className={styles.cursor} />}
                </div>
              )}

              {msg.sources && msg.sources.length > 0 && (
                <SourcesDrawer
                  sources={msg.sources}
                  open={expandedSources === i}
                  onToggle={() => setExpandedSources(expandedSources === i ? null : i)}
                />
              )}
            </div>
          </div>
        ))}

        <div ref={bottomRef} />
      </div>

      <div className={styles.inputArea}>
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          placeholder="Ask about the code… (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          rows={1}
        />
        <button
          className={styles.sendBtn}
          onClick={() => sendMessage(input)}
          disabled={streaming || !input.trim()}
        >
          {streaming ? <span className={styles.spinner} /> : '↑'}
        </button>
      </div>
    </div>
  )
}

function SourcesDrawer({
  sources,
  open,
  onToggle,
}: {
  sources: CodeChunk[]
  open: boolean
  onToggle: () => void
}) {
  return (
    <div className={styles.sources}>
      <button className={styles.sourcesToggle} onClick={onToggle}>
        <span className={styles.sourcesIcon}>{open ? '▾' : '▸'}</span>
        {sources.length} source{sources.length !== 1 ? 's' : ''} retrieved
      </button>
      {open && (
        <div className={styles.sourceList}>
          {sources.map((s, i) => (
            <div key={i} className={styles.sourceItem}>
              <div className={styles.sourceHeader}>
                <code className={styles.sourcePath}>{s.file_path}</code>
                <span className={styles.sourceScore}>{(s.score * 100).toFixed(0)}%</span>
              </div>
              <SyntaxHighlighter
                style={oneDark as Record<string, React.CSSProperties>}
                language={s.language || 'text'}
                PreTag="div"
                customStyle={{ margin: 0, fontSize: '0.75rem', borderRadius: '4px' }}
              >
                {s.content.slice(0, 600)}
              </SyntaxHighlighter>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
