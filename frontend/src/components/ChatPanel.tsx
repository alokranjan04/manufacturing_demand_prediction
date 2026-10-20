import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'
import { sendChatMessage } from '../api/chat'
import type { ChatTurnHistory } from '../api/types'

interface Turn {
  id: string
  role: 'user' | 'assistant'
  content: string
  error?: string
  pending?: boolean
}

interface QuickAction {
  id: string
  label: string
  question: string
}

function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (error.response) return `Request failed (${error.response.status}).`
  }
  return 'Something went wrong. Please try again.'
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'demand_at_risk',
    label: 'Demand at risk by region',
    question: 'Which regions have the highest demand at risk based on recent forecast deviations?',
  },
  {
    id: 'top_deviation_skus',
    label: 'Highest deviation SKUs',
    question: 'Which SKUs show the largest forecast deviations compared to the prior run?',
  },
  {
    id: 'inventory_cover',
    label: 'Inventory cover status',
    question: 'What is the current average inventory cover in days across active SKUs, and which are below safety stock?',
  },
  {
    id: 'pending_actions',
    label: 'Pending supply actions',
    question: 'What supply actions are currently pending human approval from the agent?',
  },
  {
    id: 'forecast_accuracy',
    label: 'Forecast model accuracy',
    question: 'What is the current forecast accuracy (MAPE) of the LightGBM champion model?',
  },
]

const REGIONS = ['All', 'APAC', 'EMEA', 'AMER'] as const
type Region = (typeof REGIONS)[number]

function applyRegion(question: string, region: Region): string {
  if (region === 'All') return question
  return `${question} Focus specifically on the ${region} region only.`
}

function ChatPanel() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)
  const [input, setInput] = useState('')
  const [region, setRegion] = useState<Region>('All')

  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  async function runTurn(question: string) {
    if (busy) return
    setBusy(true)

    const userId = `${Date.now()}-u`
    const assistantId = `${Date.now()}-a`
    setTurns((prev) => [
      ...prev,
      { id: userId, role: 'user', content: question },
      { id: assistantId, role: 'assistant', content: '', pending: true },
    ])

    const history: ChatTurnHistory[] = turns
      .filter((turn) => !turn.pending && !turn.error)
      .map((turn) => ({ role: turn.role, content: turn.content }))

    try {
      const result = await sendChatMessage(question, history)
      setTurns((prev) =>
        prev.map((turn) => (turn.id === assistantId ? { ...turn, content: result.answer, pending: false } : turn)),
      )
    } catch (error) {
      setTurns((prev) =>
        prev.map((turn) =>
          turn.id === assistantId ? { ...turn, pending: false, error: describeError(error) } : turn,
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  function handleSend() {
    const message = input.trim()
    if (!message || busy) return
    setInput('')
    void runTurn(applyRegion(message, region))
  }

  return (
    <div className="panel chat-panel">
      <h2>Ask the analytics assistant</h2>

      <div className="chat-scope-row">
        <p className="scope-note">
          Scope: <strong>Chemical Manufacturing — {region === 'All' ? 'all SKUs & regions' : `${region} region`}</strong>
        </p>
        <div className="region-filter">
          <label htmlFor="region-select">Region:</label>
          <select
            id="region-select"
            value={region}
            onChange={(e) => setRegion(e.target.value as Region)}
            disabled={busy}
          >
            {REGIONS.map((r) => (
              <option key={r} value={r}>{r === 'All' ? 'All regions' : r}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="quick-actions">
        {QUICK_ACTIONS.map((action) => (
          <button
            key={action.id}
            type="button"
            className="chip"
            disabled={busy}
            onClick={() => void runTurn(applyRegion(action.question, region))}
          >
            {action.label}
          </button>
        ))}
      </div>

      <div className="conversation chat-conversation">
        {turns.length === 0 && (
          <p className="empty-hint">Ask a question above, or click a quick-question button to get started.</p>
        )}
        {turns.map((turn) => (
          <div key={turn.id} className={`chat-bubble chat-bubble--${turn.role}`}>
            {turn.pending ? (
              <span className="spinner" aria-label="Thinking" />
            ) : turn.error ? (
              <span className="error-text">{turn.error}</span>
            ) : (
              <ReactMarkdown>{turn.content}</ReactMarkdown>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className="chat-input-row"
        onSubmit={(event) => {
          event.preventDefault()
          handleSend()
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about demand, inventory, forecasts, or supply actions…"
          disabled={busy}
        />
        <button type="submit" className="counter" disabled={busy || !input.trim()}>
          {busy ? 'Thinking…' : 'Send'}
        </button>
      </form>
    </div>
  )
}

export default ChatPanel
