import { useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'

const apiBase = import.meta.env.VITE_API_URL || '/api'

const headersWithAuth = (token) =>
  token
    ? {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
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

  useEffect(() => {
    localStorage.setItem('angadgpt_token', token)
  }, [token])

  useEffect(() => {
    fetch(`${apiBase}/health`)
      .then((res) => res.json())
      .then(() => setStatus('online'))
      .catch(() => setStatus('offline'))
  }, [])

  useEffect(() => {
    if (!scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, isSending])

  const normalizeAssistantContent = (data) => {
    if (!data) return ''
    if (typeof data.content === 'string') {
      const raw = data.content.trim()
      if (raw.startsWith('{') && raw.includes('"action"') && raw.includes('"content"')) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed && parsed.action === 'respond' && typeof parsed.content === 'string') {
            return parsed.content
          }
        } catch {
          // Fall through to raw content
        }
      }
      return data.content
    }
    if (typeof data === 'object' && data.action === 'respond' && typeof data.content === 'string') {
      return data.content
    }
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
      const res = await fetch(`${apiBase}/agent/step`, {
        method: 'POST',
        headers: apiHeaders,
        body: JSON.stringify({ message: input })
      })
      if (!res.ok) {
        const text = await res.text()
        setAgentError(`API error ${res.status}: ${text}`)
        return
      }
      const data = await res.json()
      const content = normalizeAssistantContent(data)
      setMessages((prev) => [...prev, { role: 'assistant', content }])
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
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-cobalt/20 border border-cobalt/40 grid place-items-center">
            <span className="text-cobalt font-bold">A</span>
          </div>
          <div>
            <div className="text-sm uppercase tracking-[0.3em] text-haze/60">AngadGPT Nexus</div>
            <div className="text-lg font-semibold">Chat</div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className={`text-xs ${status === 'online' ? 'text-emerald-400' : 'text-ember'}`}>
            {status}
          </div>
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Auth token (optional)"
            className="bg-transparent border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-cobalt"
          />
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-6 py-6" ref={scrollRef}>
        <div className="max-w-3xl mx-auto flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="glass rounded-2xl p-6 text-haze/70">
              <div className="text-sm uppercase tracking-[0.2em] text-haze/50">Welcome</div>
              <h2 className="text-2xl font-semibold mt-2">Talk to Nexus</h2>
              <p className="mt-2 text-sm text-haze/70">
                Ask anything. Try: “list files”, “read repo/README.md”, or “run repo/scripts/train.py”.
              </p>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-cobalt/20 border border-cobalt/40 self-end'
                  : 'bg-white/5 border border-white/10 self-start'
              }`}
            >
              {msg.role === 'assistant' ? (
                <ReactMarkdown
                  className="markdown"
                  remarkPlugins={[remarkGfm, remarkBreaks]}
                >
                  {msg.content}
                </ReactMarkdown>
              ) : (
                <div className="whitespace-pre-wrap font-sans">{msg.content}</div>
              )}
            </div>
          ))}

          {isSending && (
            <div className="max-w-[60%] rounded-2xl px-4 py-3 text-sm bg-white/5 border border-white/10 self-start">
              Nexus is thinking...
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-white/10 px-6 py-4">
        <div className="max-w-3xl mx-auto flex flex-col gap-2">
          {agentError && (
            <div className="text-xs text-ember border border-ember/40 rounded-lg p-2">
              {agentError}
            </div>
          )}
          <div className="flex gap-3">
            <textarea
              value={agentInput}
              onChange={(e) => setAgentInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Send a message..."
              className="flex-1 bg-transparent border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-cobalt"
            />
            <button
              onClick={sendAgent}
              className="bg-ember text-obsidian font-semibold px-5 rounded-xl hover:opacity-90"
              disabled={isSending}
            >
              Send
            </button>
          </div>
          <div className="text-xs text-haze/50">
            Press Enter to send, Shift+Enter for a new line.
          </div>
        </div>
      </footer>
    </div>
  )
}
