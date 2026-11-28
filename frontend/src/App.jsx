import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import remarkBreaks from 'remark-breaks'
import rehypeKatex from 'rehype-katex'

const apiBase = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const DEFAULT_MESSAGES_KEY = 'angadgpt_messages'
const MAX_SAVED_MESSAGES = 200
const MAX_THREADS = 200
const HEALTH_INTERVAL_MS = 30000
const MAX_ATTACHMENTS = 3
const MAX_IMAGE_EDGE = 1200
const VISION_MODEL_LABEL = 'qwen/qwen3.8-27b'

const TOOL_LABELS = {
  files: 'Files',
  workspace: 'Workspace',
  search: 'Search',
  repos: 'Repositories',
  scripts: 'Scripts',
  calendar: 'Calendar',
}

// Groq caps an image request at 20MB and counts base64 as ~33% overhead, so
// large photos are downscaled in the browser before they are sent.
async function prepareImage(file) {
  const source = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Could not read that image.'))
    reader.readAsDataURL(file)
  })
  const element = await new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('That file is not a readable image.'))
    image.src = source
  })
  const scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(element.width, element.height))
  if (scale >= 1 && source.length < 1200000) return source
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(element.width * scale))
  canvas.height = Math.max(1, Math.round(element.height * scale))
  canvas.getContext('2d').drawImage(element, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.85)
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

const newThreadId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`

const emptyThread = () => ({ id: newThreadId(), messages: [], updatedAt: Date.now() })

const threadTitle = (thread) => {
  const first = (thread?.messages || []).find((message) => message.role === 'user')?.content
  return first ? String(first).replace(/\s+/g, ' ').slice(0, 42) : 'New chat'
}

// Every conversation is its own entry, so starting a new chat never replaces an
// older transcript. Single transcripts saved by earlier versions become one.
const loadThreads = (key, legacyKey) => {
  let threads = []
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || '[]')
    if (Array.isArray(parsed)) {
      threads = parsed
        .filter((thread) => thread && typeof thread.id === 'string' && Array.isArray(thread.messages))
        .slice(0, MAX_THREADS)
        .map((thread) => ({
          id: thread.id,
          messages: thread.messages.slice(-MAX_SAVED_MESSAGES),
          updatedAt: Number(thread.updatedAt) || Date.now(),
        }))
    }
  } catch {
    threads = []
  }
  if (threads.length === 0) {
    const legacy = loadSavedMessages(legacyKey)
    if (legacy.length > 0) {
      threads = [{ id: newThreadId(), messages: legacy, updatedAt: Date.now() }]
    }
  }
  return threads
}

const makeThreadStore = (key, legacyKey) => {
  const threads = loadThreads(key, legacyKey)
  const withBlank = threads.length > 0 ? threads : [emptyThread()]
  return { key, threads: withBlank, activeId: withBlank[0].id }
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
  const threadsKey = `${messagesKey}:threads`
  const [status, setStatus] = useState('booting')
  const [agentInput, setAgentInput] = useState('')
  const [threadStore, setThreadStore] = useState(() => makeThreadStore(threadsKey, messagesKey))
  const [agentError, setAgentError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [attachments, setAttachments] = useState([])
  const scrollRef = useRef(null)
  const textareaRef = useRef(null)
  const fileInputRef = useRef(null)
  const threads = threadStore.key === threadsKey ? threadStore.threads : []
  const activeId = threadStore.key === threadsKey ? threadStore.activeId : ''
  const activeThread = threads.find((thread) => thread.id === activeId) || null
  const messages = activeThread ? activeThread.messages : []
  const visibleThreads = threads.filter((thread) => thread.messages.length > 0)
  const activeIdRef = useRef(activeId)
  const messagesRef = useRef(messages)
  const chatTitle = activeThread ? threadTitle(activeThread) : 'New chat'

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
    activeIdRef.current = activeId
  }, [activeId])

  // Every write goes through the store, so each conversation keeps its own
  // transcript and only the active one changes.
  const updateMessages = (next) => {
    const id = activeIdRef.current
    if (!id) return
    setThreadStore((prev) => {
      if (prev.key !== threadsKey) return prev
      return {
        ...prev,
        threads: prev.threads.map((thread) => {
          if (thread.id !== id) return thread
          const nextMessages = typeof next === 'function' ? next(thread.messages) : next
          return { ...thread, messages: nextMessages.slice(-MAX_SAVED_MESSAGES), updatedAt: Date.now() }
        }),
      }
    })
  }

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
        // Saved conversations win: restoring the server transcript into a blank
        // thread would duplicate one that is already in Recent.
        if (threadStore.threads.some((thread) => thread.messages.length > 0)) return
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
        updateMessages(restored)
      } catch (error) {
        if (!cancelled) setAgentError(error?.message || 'Could not load your saved conversation.')
      }
    }
    loadServerMemory()
    return () => { cancelled = true }
  }, [getToken, messagesKey])

  useEffect(() => {
    if (threadStore.key !== threadsKey) return
    // Attached images are large base64 strings: keep them out of localStorage.
    const persistable = (threads, maxThreads, maxMessages) =>
      threads.slice(0, maxThreads).map((thread) => ({
        ...thread,
        messages: thread.messages
          .slice(-maxMessages)
          .map(({ role, content, tool }) => ({ role, content, tool })),
      }))
    try {
      localStorage.setItem(
        threadsKey,
        JSON.stringify(persistable(threadStore.threads, threadStore.threads.length, MAX_SAVED_MESSAGES)),
      )
    } catch {
      try {
        // Too big for the storage quota: keep fewer conversations rather than
        // letting one oversized write stop every future save.
        localStorage.setItem(threadsKey, JSON.stringify(persistable(threadStore.threads, 10, 20)))
      } catch {
        // Storage can be full or disabled; the chat still works in memory.
      }
    }
  }, [threadStore, threadsKey])

  const startNewChat = async () => {
    if (isSending) return
    // A new chat is a new entry; the previous transcript stays under Recent.
    const fresh = emptyThread()
    // Never drop an older transcript here; only the storage fallback trims.
    setThreadStore((prev) => ({ ...prev, threads: [fresh, ...prev.threads], activeId: fresh.id }))
    setAgentError('')
    setAgentInput('')
    setAttachments([])
    try {
      const response = await fetch(`${apiBase}/api/memory/reset`, {
        method: 'POST',
        headers: await buildHeaders(getToken),
      })
      if (!response.ok) throw new Error(errorDetail(await response.text()))
    } catch (error) {
      setAgentError(`Started a new chat, but Nexus could not reset its memory: ${error?.message || error}`)
    }
  }

  const openThread = async (id) => {
    if (isSending || id === activeId) return
    setThreadStore((prev) => ({ ...prev, activeId: id }))
    setAgentError('')
    setAgentInput('')
    setAttachments([])
    try {
      // The backend keeps one running conversation, so the opened chat starts
      // clean instead of answering with the other chat's context.
      await fetch(`${apiBase}/api/memory/reset`, {
        method: 'POST',
        headers: await buildHeaders(getToken),
      })
    } catch {
      // The transcript still opens; only the model's running context is shared.
    }
  }

  const addImages = async (fileList) => {
    const files = Array.from(fileList || []).filter((file) => file.type.startsWith('image/'))
    if (files.length === 0) {
      setAgentError('Only image files can be attached.')
      return
    }
    const room = MAX_ATTACHMENTS - attachments.length
    if (room <= 0) {
      setAgentError(`You can attach up to ${MAX_ATTACHMENTS} images per message.`)
      return
    }
    setAgentError(files.length > room ? `Only ${MAX_ATTACHMENTS} images per message.` : '')
    try {
      const prepared = await Promise.all(
        files.slice(0, room).map(async (file) => ({
          id: `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 8)}`,
          name: file.name,
          dataUrl: await prepareImage(file),
        })),
      )
      setAttachments((prev) => [...prev, ...prepared].slice(0, MAX_ATTACHMENTS))
    } catch (error) {
      setAgentError(error?.message || 'Could not attach that image.')
    }
  }

  const removeAttachment = (id) => {
    setAttachments((prev) => prev.filter((item) => item.id !== id))
  }

  const handleFilesPicked = (event) => {
    addImages(event.target.files)
    event.target.value = ''
  }

  const sendAgent = async () => {
    const input = agentInput.trim()
    const outgoing = attachments
    if ((!input && outgoing.length === 0) || isSending) return
    const message = input || 'Describe this image.'
    const images = outgoing.map((item) => item.dataUrl)
    setAgentInput('')
    setAttachments([])
    setAgentError('')
    setIsSending(true)
    updateMessages((prev) => [...prev, { role: 'user', content: message, images }])
    try {
      const res = await fetch(`${apiBase}/api/agent/step`, {
        method: 'POST',
        headers: await buildHeaders(getToken),
        body: JSON.stringify({ message, images }),
      })
      if (!res.ok) {
        setAgentError(`Request failed (${res.status}): ${errorDetail(await res.text())}`)
        return
      }
      const data = await res.json()
      const reply = formatReply(data)
      updateMessages((prev) => [...prev, { role: 'assistant', content: reply.content, tool: reply.tool }])
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
        <div className="history-list">
          {visibleThreads.map((thread) => (
            <button
              key={thread.id}
              type="button"
              className={thread.id === activeId ? 'history-item active' : 'history-item'}
              onClick={() => openThread(thread.id)}
              disabled={isSending}
              title={threadTitle(thread)}
            >
              <span className="history-dot" />
              <span className="history-title">{threadTitle(thread)}</span>
            </button>
          ))}
        </div>
        {visibleThreads.length === 0 && <div className="sidebar-note">Your conversations will appear here.</div>}
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
                  ) : (
                    <div className="user-bubble">
                      {msg.images?.length ? (
                        <div className="user-images">
                          {msg.images.map((src, imageIndex) => (
                            <img key={imageIndex} className="user-image" src={src} alt={`Attachment ${imageIndex + 1}`} />
                          ))}
                        </div>
                      ) : null}
                      {msg.content}
                    </div>
                  )}
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
              {attachments.length > 0 && (
                <div className="attachment-row">
                  {attachments.map((item) => (
                    <div key={item.id} className="attachment">
                      <img src={item.dataUrl} alt={item.name} />
                      <button type="button" className="attachment-remove" onClick={() => removeAttachment(item.id)} aria-label={`Remove ${item.name}`}>×</button>
                    </div>
                  ))}
                  <span className="attachment-model">Vision model · {VISION_MODEL_LABEL}</span>
                </div>
              )}
              <textarea
                ref={textareaRef}
                value={agentInput}
                onChange={(e) => setAgentInput(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                placeholder="Message Nexus…"
                aria-label="Message Nexus"
              />
              <div className="composer-tools">
                <div className="composer-actions">
                  <button type="button" className="attach-button" onClick={() => fileInputRef.current?.click()} disabled={isSending} aria-label="Attach an image" title="Attach an image">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d="M20.5 11.5 11.9 20a5.4 5.4 0 0 1-7.6-7.6l8.7-8.7a3.6 3.6 0 0 1 5.1 5.1l-8.7 8.7a1.8 1.8 0 0 1-2.5-2.5l8-8" />
                    </svg>
                  </button>
                  <span className="composer-hint">↵ to send · ⇧↵ for a new line</span>
                </div>
                <button className="send-button" onClick={sendAgent} disabled={isSending || (!agentInput.trim() && attachments.length === 0)} aria-label="Send message">↑</button>
              </div>
              <input ref={fileInputRef} className="visually-hidden" type="file" accept="image/*" multiple onChange={handleFilesPicked} tabIndex={-1} />
            </div>
            <div className="composer-disclaimer">Nexus can make mistakes. Check important information.</div>
          </div>
        </footer>
      </section>
    </div>
  )
}
