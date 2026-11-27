import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'

const apiBase = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const headersWithAuth = (token) => token
  ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  : { 'Content-Type': 'application/json' }

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('angadgpt_token') || '')
  const [status, setStatus] = useState('booting')
  const [agentInput, setAgentInput] = useState('')
  const [messages, setMessages] = useState([])
  const [agentError, setAgentError] = useState('')
  const [isSending, setIsSending] = useState(false)
  const scrollRef = useRef(null)
  const apiHeaders = useMemo(() => headersWithAuth(token), [token])
  const firstUserMessage = messages.find((message) => message.role === 'user')?.content
  const chatTitle = firstUserMessage ? firstUserMessage.replace(/\s+/g, ' ').slice(0, 42) : 'New chat'

  useEffect(() => { localStorage.setItem('angadgpt_token', token) }, [token])
  useEffect(() => {
    fetch(`${apiBase}/api/health`).then((res) => res.json()).then(() => setStatus('online')).catch(() => setStatus('offline'))
  }, [])
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, isSending])

  const normalizeAssistantContent = (data) => {
    if (!data) return ''
    if (typeof data.content === 'string') {
      const raw = data.content.trim()
      if (raw.startsWith('{') && raw.includes('"action"') && raw.includes('"content"')) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed?.action === 'respond' && typeof parsed.content === 'string') return parsed.content
        } catch { /* Use the original response when it is not JSON. */ }
      }
      return data.content
    }
    if (typeof data === 'object' && data.action === 'respond' && typeof data.content === 'string') return data.content
    return JSON.stringify(data, null, 2)
  }

  const sendAgent = async () => {
    if (!agentInput.trim()) return
    const input = agentInput
    setAgentInput('')
    setAgentError('')
    setIsSending(true)
    setMessages((prev) => [...prev, { role: 'user', content: input }])
    try {
      const res = await fetch(`${apiBase}/api/agent/step`, {
        method: 'POST', headers: apiHeaders, body: JSON.stringify({ message: input })
      })
      if (!res.ok) {
        const text = await res.text()
        setAgentError(`API error ${res.status}: ${text}`)
        return
      }
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', content: normalizeAssistantContent(data) }])
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
        <div className="brand-row"><div className="brand-mark">N</div><span>Nexus</span><span className="sidebar-chevron">⌄</span></div>
        <button className="new-chat" onClick={() => window.location.reload()}><span>＋</span> New chat</button>
        <div className="sidebar-section">Recent</div>
        {messages.length > 0 && <div className="history-item active"><span className="history-dot" />{chatTitle}</div>}
        <div className="sidebar-note">Your conversations will appear here.</div>
        <div className="sidebar-bottom">
          <label className="token-label" htmlFor="auth-token">API access</label>
          <input id="auth-token" value={token} onChange={(e) => setToken(e.target.value)} placeholder="Auth token (optional)" />
          <div className="connection"><i className={status} />{status === 'booting' ? 'Connecting…' : status === 'online' ? 'Connected' : 'Offline'}</div>
        </div>
      </aside>

      <section className="chat-workspace">
        <header className="topbar">
          <div className="mobile-brand">Nexus</div>
          <div className="chat-heading"><span>{chatTitle}</span><span className="heading-chevron">⌄</span></div>
          <div className="model-pill"><span className="model-spark">✳</span><span>Nexus AI</span><span className="model-caret">⌄</span></div>
        </header>

        <main className="conversation" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-symbol">✳</div>
              <h1>What can I help you with?</h1>
              <p>Ask a question, explore an idea, or work on a project.</p>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((msg, idx) => (
                <article key={idx} className={`message ${msg.role}`}>
                  {msg.role === 'assistant' ? <><div className="assistant-avatar">✳</div><ReactMarkdown className="markdown" remarkPlugins={[remarkGfm, remarkBreaks]}>{msg.content}</ReactMarkdown></> : <div className="user-bubble">{msg.content}</div>}
                </article>
              ))}
              {isSending && <article className="message assistant"><div className="assistant-avatar">✳</div><div className="thinking"><span /><span /><span /></div></article>}
            </div>
          )}
        </main>

        <footer className="composer-area">
          <div className="composer-wrap">
            {agentError && <div className="error-message">{agentError}</div>}
            <div className="composer">
              <textarea value={agentInput} onChange={(e) => setAgentInput(e.target.value)} onKeyDown={handleKeyDown} rows={1} placeholder="Message Nexus…" aria-label="Message Nexus" />
              <div className="composer-tools"><span className="composer-hint">↵ to send · ⇧↵ for a new line</span><button className="send-button" onClick={sendAgent} disabled={isSending || !agentInput.trim()} aria-label="Send message">↑</button></div>
            </div>
            <div className="composer-disclaimer">Nexus can make mistakes. Check important information.</div>
          </div>
        </footer>
      </section>
    </div>
  )
}
