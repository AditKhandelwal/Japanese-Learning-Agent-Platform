import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { streamChat, type ChatEvent } from '../lib/api'
import './SessionPage.css'

const MODE_META: Record<string, { name: string; kanji: string; gradient: string; glow: string; border: string }> = {
  lesson:       { name: 'Lesson',       kanji: '学', gradient: 'linear-gradient(135deg, #ff6b9d, #ff9f43)', glow: 'rgba(255, 107, 157, 0.15)', border: 'rgba(255, 107, 157, 0.3)' },
  recall:       { name: 'Recall',       kanji: '復', gradient: 'linear-gradient(135deg, #ff9f43, #e056fd)', glow: 'rgba(255, 159, 67, 0.15)',  border: 'rgba(255, 159, 67, 0.3)'  },
  reading:      { name: 'Reading',      kanji: '読', gradient: 'linear-gradient(135deg, #e056fd, #48dbfb)', glow: 'rgba(224, 86, 253, 0.15)',  border: 'rgba(224, 86, 253, 0.25)' },
  production:   { name: 'Production',   kanji: '書', gradient: 'linear-gradient(135deg, #48dbfb, #1dd1a1)', glow: 'rgba(72, 219, 251, 0.15)',  border: 'rgba(72, 219, 251, 0.25)' },
  conversation: { name: 'Conversation', kanji: '話', gradient: 'linear-gradient(135deg, #1dd1a1, #ff6b9d)', glow: 'rgba(29, 209, 161, 0.15)',  border: 'rgba(29, 209, 161, 0.25)' },
}

type Message =
  | { id: string; role: 'user'; content: string }
  | { id: string; role: 'agent'; content: string; streaming: boolean }
  | { id: string; role: 'tool'; toolName: string; done: boolean }

interface Props {
  sessionId: string
  userId: string
  mode: string
  onEnd: () => void
}

let _seq = 0
const uid = () => String(++_seq)

export default function SessionPage({ sessionId, userId, mode, onEnd }: Props) {
  const meta = MODE_META[mode] ?? MODE_META.lesson
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const greeted = useRef(false)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!greeted.current) { greeted.current = true; runStream('begin', true) } }, [])

  async function runStream(text: string, silent = false) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)

    if (!silent) {
      setMessages(prev => [...prev, { id: uid(), role: 'user', content: text }])
    }

    const agentId = uid()
    let activeToolId: string | null = null

    setMessages(prev => [...prev, { id: agentId, role: 'agent', content: '', streaming: true }])

    try {
      await streamChat({ userId, sessionId, mode, message: text }, (event: ChatEvent) => {
        if (event.type === 'text' && event.content) {
          setMessages(prev => prev.map(m =>
            m.id === agentId && m.role === 'agent'
              ? { ...m, content: m.content + event.content! }
              : m
          ))
        } else if (event.type === 'tool_call' && event.name) {
          activeToolId = uid()
          const tid = activeToolId
          setMessages(prev => [...prev, { id: tid, role: 'tool', toolName: event.name!, done: false }])
        } else if (event.type === 'tool_result' && activeToolId) {
          const tid = activeToolId
          setMessages(prev => prev.map(m =>
            m.id === tid && m.role === 'tool' ? { ...m, done: true } : m
          ))
          activeToolId = null
        }
      })
    } catch (err) {
      console.error('Stream error', err)
      setMessages(prev => prev.map(m =>
        m.id === agentId && m.role === 'agent'
          ? { ...m, content: m.content || 'Something went wrong — please try again.', streaming: false }
          : m
      ))
    }

    setMessages(prev => prev.map(m =>
      m.id === agentId && m.role === 'agent' ? { ...m, streaming: false } : m
    ))
    busyRef.current = false
    setBusy(false)
  }

  async function handleSend() {
    const text = input.trim()
    if (!text || busyRef.current) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    await runStream(text)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleInputChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value)
    const ta = e.target
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`
  }

  const showConnecting = messages.length === 0

  return (
    <div className="sess-root" style={{ '--mode-glow': meta.glow, '--mode-border': meta.border } as CSSProperties}>
      {/* Header */}
      <header className="sess-header">
        <div className="sess-logo">
          <span className="sess-logo-ja">先生AI</span>
          <span className="sess-logo-en">Japanese Tutor</span>
        </div>
        <div className="sess-mode-badge">
          <span
            className="sess-mode-kanji"
            style={{ background: meta.gradient, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}
          >
            {meta.kanji}
          </span>
          <span className="sess-mode-name">{meta.name}</span>
        </div>
        <button className="sess-end-btn" onClick={onEnd}>← Dashboard</button>
      </header>

      {/* Messages */}
      <main className="sess-messages">
        {showConnecting ? (
          <div className="sess-connecting">
            <div className="sess-dots"><span /><span /><span /></div>
          </div>
        ) : (
          messages.map(msg => {
            if (msg.role === 'user') {
              return (
                <div key={msg.id} className="sess-row sess-row--user">
                  <div className="sess-bubble sess-bubble--user">{msg.content}</div>
                </div>
              )
            }
            if (msg.role === 'agent') {
              return (
                <div key={msg.id} className="sess-row sess-row--agent">
                  <div
                    className="sess-avatar"
                    style={{ background: meta.gradient }}
                  >
                    {meta.kanji}
                  </div>
                  <div className="sess-bubble sess-bubble--agent">
                    {msg.content}
                    {msg.streaming && <span className="sess-cursor" />}
                  </div>
                </div>
              )
            }
            if (msg.role === 'tool') {
              return (
                <div key={msg.id} className="sess-row sess-row--tool">
                  <span className={`sess-tool-chip ${msg.done ? 'sess-tool-chip--done' : 'sess-tool-chip--active'}`}>
                    {msg.done ? '✓' : '⟳'} {msg.toolName}
                  </span>
                </div>
              )
            }
            return null
          })
        )}
        <div ref={bottomRef} />
      </main>

      {/* Input */}
      <footer className="sess-footer">
        <div className="sess-input-row">
          <textarea
            ref={textareaRef}
            className="sess-textarea"
            placeholder={busy ? 'Sensei is responding…' : 'Type your answer or ask a question… (Enter to send)'}
            rows={1}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={busy}
          />
          <button
            className="sess-send-btn"
            style={{ background: meta.gradient }}
            onClick={handleSend}
            disabled={!input.trim() || busy}
          >
            Send →
          </button>
        </div>
      </footer>
    </div>
  )
}