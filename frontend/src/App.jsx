import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkBreaks from 'remark-breaks'
import rehypeKatex from 'rehype-katex'

const apiBase = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const DEFAULT_MESSAGES_KEY = 'angadgpt_messages'
const MAX_SAVED_MESSAGES = 200
const HEALTH_INTERVAL_MS = 30000

const TOOL_LABELS = {
  files: 'Files',
  workspace: 'Workspace',
  search: 'Search',
  repos: 'Repositories',
  scripts: 'Scripts',
  calendar: 'Calendar',
}

async function buildHeaders(getToken) {
  if (!getToken) throw new Error('Clerk is not configured for this app.')
  const sessionToken = await getToken()
  if (!sessionToken) throw new Error('Your sign-in session has expired. Sign in again.')
  return { Authorization: `Bearer ${sessionToken}`, 'Content-Type': 'application/json' }
}

const fenced = (language, text) => {
  const body = String(text ?? '').replace(/```/g, '` ` `')
  return '```' + language + '\n' + body + '\n```'
}

const loadSavedMessages = (key) => {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || '[]')
    return Array.isArray(parsed) ? parsed.slice(-MAX_SAVED_MESSAGES) : []
  } catch {
    return []
  }
}

const unwrapContent = (raw) => {
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{') || !trimmed.includes('"content"')) return raw
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed && typeof parsed.content === 'string' && (parsed.action === 'respond' || !parsed.action)) {
      return parsed.content
    }
  } catch {
    // Plain text that merely starts with a brace.
  }
  return raw
}

// Matches fenced code blocks and inline code so math fixes never touch them.
const CODE_SPLIT = /(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/g
const MATH_ENVS =
  'equation\\*?|align\\*?|alignat\\*?|gather\\*?|multline\\*?|flalign\\*?|cases|aligned|gathered|split|array|[pbBvV]?matrix|smallmatrix'
const BARE_ENV = new RegExp(`\\\\begin\\{(${MATH_ENVS})\\}[\\s\\S]*?\\\\end\\{\\1\\}`, 'g')
const mathCache = new Map()

// Models mix \(…\), \[…\] and bare \begin{…} blocks with $…$ / $$…$$.
// remark-math only understands dollar delimiters, so convert to those.
function normalizeMathText(text) {
  const held = []
  const hold = (value) => `\u0000${held.push(value) - 1}\u0000`
  const converted = text
    .replace(/\$\$[\s\S]*?\$\$/g, hold)
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, body) => hold(`$$\n${body.trim()}\n$$`))
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, body) => hold(`$${body.replace(/\s*\n\s*/g, ' ').trim()}$`))
    .replace(BARE_ENV, (block) => hold(`$$\n${block.trim()}\n$$`))
  return converted.replace(/\u0000(\d+)\u0000/g, (_, index) => held[Number(index)] ?? '')
}

function normalizeMath(content) {
  const source = typeof content === 'string' ? content : ''
  if (!source.includes('\\')) return source
  if (mathCache.has(source)) return mathCache.get(source)
  const parts = source.split(CODE_SPLIT)
  const result = parts.map((part, index) => (index % 2 === 1 ? part : normalizeMathText(part))).join('')
  if (mathCache.size > 400) mathCache.clear()
  mathCache.set(source, result)
  return result
}

function describeToolResult(result) {
  if (result === null || result === undefined) return '_No output._'
  if (typeof result !== 'object') return String(result)
  if (result.error) return `**Error:** ${result.error}`

  if (Array.isArray(result.items)) {
    return result.items.length
      ? result.items.map((item) => `- \`${item}\``).join('\n')
      : '_Nothing here._'
  }
  if (Array.isArray(result.matches)) {
    return result.matches.length ? fenced('text', result.matches.join('\n')) : '_No matches._'
  }
  if (Array.isArray(result.repos)) {
    return result.repos.length
      ? result.repos.map((repo) => `- \`${repo.name}\`${repo.is_git ? '' : ' _(folder)_'}`).join('\n')
      : '_No repositories._'
  }
  if (Array.isArray(result.events)) {
    return result.events.length
      ? result.events.map((event) => `- **${event.title}** · ${event.start_time}`).join('\n')
      : '_No events._'
  }
  if (result.event) return `Saved **${result.event.title}**.`
  if (result.deleted !== undefined) return result.deleted ? 'Deleted the event.' : 'Nothing to delete.'

  if (typeof result.diff === 'string') {
    return result.diff ? fenced('diff', result.diff) : '_No changes._'
  }
  if (typeof result.content === 'string') {
    const label = result.path ? `**\`${result.path}\`**\n\n` : ''
    return label + fenced('', result.content)
  }
  if (result.returncode !== undefined) {
    const output = [result.stdout, result.stderr].filter(Boolean).join('\n').trim()
    return `**Exit code ${result.returncode}**\n\n` + fenced('text', output || 'No output.')
  }
  if (result.written) return `Wrote \`${result.path}\`.`
  if (result.appended) return `Appended to \`${result.path}\`.`
  if (result.created) return `Created \`${result.path}\`.`

  return fenced('json', JSON.stringify(result, null, 2))
}

function formatReply(data) {
  if (!data) return { content: '', tool: '' }
  if (data.type === 'tool') {
    return { content: describeToolResult(data.result), tool: data.tool || 'tool' }
  }
  if (typeof data.content === 'string') {
    return { content: unwrapContent(data.content), tool: '' }
  }
  if (data.action === 'respond' && typeof data.content === 'string') {
    return { content: data.content, tool: '' }
  }
  return { content: fenced('json', JSON.stringify(data, null, 2)), tool: '' }
}

function errorDetail(body) {
  try {
    const parsed = JSON.parse(body)
    if (parsed && parsed.detail) {
      return typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail)
    }
  } catch {
    // Not JSON: show the raw body.
  }
  return body
}

export default function App({ getToken, storageKey = DEFAULT_MESSAGES_KEY, accountControl = null }) {
  const messagesKey = storageKey || DEFAULT_MESSAGES_KEY
  const [status, setStatus] = useState('booting')
  const [agentInput, setAgentInput] = useState('')
  const [messages, setMessages] = useState(() => loadSavedMessages(messagesKey))
  const [agentError, setAgentError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const scrollRef = useRef(null)
  const textareaRef = useRef(null)
  const messagesRef = useRef(messages)
  const firstUserMessage = messages.find((message) => message.role === 'user')?.content
  const chatTitle = firstUserMessage ? String(firstUserMessage).replace(/\s+/g, ' ').slice(0, 42) : 'New chat'

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const res = await fetch(`${apiBase}/api/health`)
        if (!res.ok) throw new Error(String(res.status))
        if (!cancelled) setStatus('online')
      } catch {
        if (!cancelled) setStatus('offline')
      }
    }
    check()
    const timer = setInterval(check, HEALTH_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, isSending])

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`
  }, [agentInput])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  useEffect(() => {
    let cancelled = false
    const loadServerMemory = async () => {
      try {
        const response = await fetch(`${apiBase}/api/memory`, {
          headers: await buildHeaders(getToken),
        })
        if (!response.ok) throw new Error(errorDetail(await response.text()))
        const data = await response.json()
        if (cancelled || messagesRef.current.length > 0) return
        const restored = (data.messages || []).flatMap((message) => {
          if (message.role === 'user' || message.role === 'assistant') {
            return [{ role: message.role, content: message.content }]
          }
          if (message.role === 'tool') {
            try {
              const result = JSON.parse(message.content)
              return [{
                role: 'assistant',
                tool: result.tool || 'tool',
                content: describeToolResult(result.result ?? result),
              }]
            } catch {
              return []
            }
          }
          return []
        }).slice(-MAX_SAVED_MESSAGES)
        setMessages(restored)
      } catch (error) {
        if (!cancelled) setAgentError(error?.message || 'Could not load your saved conversation.')
      }
    }
    loadServerMemory()
    return () => { cancelled = true }
  }, [getToken, messagesKey])

  useEffect(() => {
    try {
      localStorage.setItem(messagesKey, JSON.stringify(messages.slice(-MAX_SAVED_MESSAGES)))
    } catch {
      // Storage can be full or disabled; the chat still works in memory.
    }
  }, [messages, messagesKey])

  const startNewChat = async () => {
    if (isSending) return
    try {
      const response = await fetch(`${apiBase}/api/memory/reset`, {
        method: 'POST',
        headers: await buildHeaders(getToken),
      })
      if (!response.ok) throw new Error(errorDetail(await response.text()))
      setMessages([])
      setAgentError('')
      setAgentInput('')
      localStorage.removeItem(messagesKey)
    } catch (error) {
      setAgentError(`Could not start a fresh conversation: ${error?.message || error}`)
    }
  }

  const sendAgent = async () => {
    const input = agentInput.trim()
    if (!input || isSending) return
    setAgentInput('')
    setAgentError('')
    setIsSending(true)
    setMessages((prev) => [...prev, { role: 'user', content: input }])
    try {
      const res = await fetch(`${apiBase}/api/agent/step`, {
        method: 'POST',
        headers: await buildHeaders(getToken),
        body: JSON.stringify({ message: input }),
      })
      if (!res.ok) {
        setAgentError(`Request failed (${res.status}): ${errorDetail(await res.text())}`)
        return
      }
      const data = await res.json()
      const reply = formatReply(data)
      setMessages((prev) => [...prev, { role: 'assistant', content: reply.content, tool: reply.tool }])
    } catch (err) {
      setAgentError(`Network error: ${err?.message || err}`)
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendAgent()
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-row"><img className="brand-mark" src="/nexus-logo.png" alt="Nexus logo" /><span>Nexus</span><span className="sidebar-chevron">⌄</span></div>
        <button className="new-chat" onClick={startNewChat} disabled={isSending}><span>＋</span> New chat</button>
        <div className="sidebar-section">Recent</div>
        {messages.length > 0 && <div className="history-item active"><span className="history-dot" />{chatTitle}</div>}
        {messages.length === 0 && <div className="sidebar-note">Your conversations will appear here.</div>}
        <div className="sidebar-bottom">
          <div className="connection"><i className={status} />{status === 'booting' ? 'Connecting…' : status === 'online' ? 'Connected' : 'Offline'}</div>
        </div>
      </aside>

      <section className="chat-workspace">
        <header className="topbar">
          <div className="mobile-brand">Nexus</div>
          <div className="chat-heading"><span>{chatTitle}</span><span className="heading-chevron">⌄</span></div>
          <div className="topbar-actions">
            <div className="model-pill"><img className="model-logo" src="/nexus-logo.png" alt="" /><span>Nexus AI</span><span className="model-caret">⌄</span></div>
            {accountControl}
          </div>
        </header>

        <main className="conversation" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="welcome">
              <img className="welcome-symbol" src="/nexus-logo.png" alt="Nexus logo" />
              <h1>What can I help you with?</h1>
              <p>Ask a question, explore an idea, or work on a project.</p>
              <p className="welcome-hint">Type <code>/help</code> to see the commands Nexus can run.</p>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((msg, idx) => (
                <article key={idx} className={`message ${msg.role}`}>
                  {msg.role === 'assistant' ? (
                    <>
                      <img className="assistant-avatar" src="/nexus-logo.png" alt="Nexus" />
                      <div className="assistant-body">
                        {msg.tool && <span className="tool-chip">{TOOL_LABELS[msg.tool] || msg.tool}</span>}
                        <div className="markdown">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
                            rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, output: 'html' }]]}
                          >
                            {normalizeMath(msg.content)}
                          </ReactMarkdown>
                        </div>
                      </div>
                    </>
                  ) : <div className="user-bubble">{msg.content}</div>}
                </article>
              ))}
              {isSending && <article className="message assistant"><img className="assistant-avatar" src="/nexus-logo.png" alt="Nexus" /><div className="thinking"><span /><span /><span /></div></article>}
            </div>
          )}
        </main>

        <footer className="composer-area">
          <div className="composer-wrap">
            {agentError && (
              <div className="error-message">
                <span>{agentError}</span>
                <button type="button" className="error-dismiss" onClick={() => setAgentError('')} aria-label="Dismiss error">×</button>
              </div>
            )}
            <div className="composer">
              <textarea
                ref={textareaRef}
                value={agentInput}
                onChange={(e) => setAgentInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder="Message Nexus…"
                aria-label="Message Nexus"
              />
              <div className="composer-tools"><span className="composer-hint">↵ to send · ⇧↵ for a new line</span><button className="send-button" onClick={sendAgent} disabled={isSending || !agentInput.trim()} aria-label="Send message">↑</button></div>
            </div>
            <div className="composer-disclaimer">Nexus can make mistakes. Check important information.</div>
          </div>
        </footer>
      </section>
    </div>
  )
}
