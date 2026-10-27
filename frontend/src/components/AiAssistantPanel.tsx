import {
  AlertCircle,
  Bot,
  Check,
  KeyRound,
  LoaderCircle,
  RotateCcw,
  Send,
  Sparkles,
  Wrench,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { getAiConfig, getErrorMessage, sendAiChatMessage, updateAiConfig } from '../api'
import type { AiConfigStatus, AiToolCallRecord, AnalyticsQueryResult } from '../types'

interface ChatEntry {
  id: string
  role: 'user' | 'assistant'
  text: string
  toolCalls?: AiToolCallRecord[]
}

interface AiAssistantPanelProps {
  onQueryResult: (result: AnalyticsQueryResult) => void
  onWarehouseUpdated: () => void
}

const SUGGESTED_PROMPTS = [
  'I would like to get detailed workforce demographic data for the united states. Include most detailed list of occupations possible and their demographic data.',
  'Find US and Euro Area CPI in DBnomics, sync to DuckDB, and compare YoY (%)',
  'Summarize the series currently stored in the DuckDB warehouse',
]

const GEMINI_MODELS = [
  { id: 'gemini-3.8-flash', label: 'Gemini 3.8 Flash (Recommended · Fast Agentic)' },
  { id: 'gemini-4-argon', label: 'Gemini 4 Argon (Deep Reasoning)' },
  { id: 'gemini-3.5-flash-lite', label: 'Gemini 3.5 Flash-Lite (High Throughput)' },
  { id: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite (Ultra Fast)' },
]

export function AiAssistantPanel({ onQueryResult, onWarehouseUpdated }: AiAssistantPanelProps) {
  const [promptInput, setPromptInput] = useState('')
  const [messages, setMessages] = useState<ChatEntry[]>([])
  const [interactionId, setInteractionId] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [error, setError] = useState('')

  const [configStatus, setConfigStatus] = useState<AiConfigStatus | null>(null)
  const [showConfigForm, setShowConfigForm] = useState(false)
  const [geminiKeyInput, setGeminiKeyInput] = useState('')
  const [fredKeyInput, setFredKeyInput] = useState('')
  const [geminiModelInput, setGeminiModelInput] = useState('gemini-3.8-flash')
  const [isSavingConfig, setIsSavingConfig] = useState(false)
  const [configSavedNotice, setConfigSavedNotice] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    getAiConfig(controller.signal)
      .then((status) => {
        setConfigStatus(status)
        setGeminiModelInput(status.gemini_model || 'gemini-3.8-flash')
      })
      .catch(() => {
        // Ignore initial config fetch errors in offline/test contexts
      })
    return () => controller.abort()
  }, [])

  async function handleSaveConfig(e: React.FormEvent): Promise<void> {
    e.preventDefault()
    setIsSavingConfig(true)
    setError('')
    setConfigSavedNotice('')
    try {
      const updated = await updateAiConfig({
        gemini_api_key: geminiKeyInput.trim() ? geminiKeyInput.trim() : undefined,
        gemini_model: geminiModelInput,
        fred_api_key: fredKeyInput.trim() ? fredKeyInput.trim() : undefined,
      })
      setConfigStatus(updated)
      setGeminiKeyInput('')
      setFredKeyInput('')
      setConfigSavedNotice('Saved to .env & hot-reloaded.')
      setTimeout(() => setConfigSavedNotice(''), 4000)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsSavingConfig(false)
    }
  }

  async function submitPrompt(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || isSending) return

    setMessages((prev) => [
      ...prev,
      { id: `user-${prev.length + 1}`, role: 'user', text: trimmed },
    ])
    setPromptInput('')
    setIsSending(true)
    setError('')

    try {
      const response = await sendAiChatMessage({
        prompt: trimmed,
        previous_interaction_id: interactionId,
      })
      setInteractionId(response.interaction_id || null)
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${prev.length + 1}`,
          role: 'assistant',
          text: response.reply,
          toolCalls: response.tool_calls,
        },
      ])

      if (response.warehouse_updated) {
        onWarehouseUpdated()
      }
      if (response.query_result) {
        onQueryResult(response.query_result)
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsSending(false)
    }
  }

  function handleResetConversation(): void {
    setMessages([])
    setInteractionId(null)
    setError('')
  }

  return (
    <section className="panel" data-testid="ai-assistant-panel">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400">
            <Sparkles size={18} />
          </div>
          <div>
            <p className="section-number">
              {configStatus?.gemini_model || 'gemini-3.8-flash'} · Interactions API
            </p>
            <h2 className="text-xl font-semibold tracking-tight">AI Economist Assistant</h2>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="secondary-button"
            onClick={() => setShowConfigForm((prev) => !prev)}
            aria-expanded={showConfigForm}
            aria-label="Configure Gemini API Key"
          >
            <KeyRound size={14} />
            {configStatus?.gemini_key_configured
              ? `API Key (${configStatus.gemini_key_masked})`
              : 'Configure API Key'}
          </button>
          {messages.length > 0 && (
            <button
              type="button"
              className="secondary-button"
              onClick={handleResetConversation}
              aria-label="Reset AI chat"
            >
              <RotateCcw size={14} /> New Chat
            </button>
          )}
        </div>
      </div>

      {showConfigForm && (
        <form
          onSubmit={(e) => void handleSaveConfig(e)}
          className="mb-4 rounded-xl border border-zinc-200 bg-zinc-50/70 p-4 dark:border-zinc-800 dark:bg-zinc-900/60"
          data-testid="ai-config-form"
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold">API Keys & Model Configuration</h3>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Keys are saved directly to your local untracked <code>.env</code> file and
                hot-reloaded immediately.
              </p>
            </div>
            {configSavedNotice && (
              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                <Check size={13} /> {configSavedNotice}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="field-label">
              Gemini API Key (AIza...)
              <input
                type="password"
                aria-label="Gemini API Key"
                placeholder={
                  configStatus?.gemini_key_masked
                    ? `Current: ${configStatus.gemini_key_masked}`
                    : 'Paste AIzaSy... key'
                }
                className="input mt-1 font-mono text-xs"
                value={geminiKeyInput}
                onChange={(e) => setGeminiKeyInput(e.target.value)}
                autoComplete="off"
              />
            </label>

            <label className="field-label">
              Gemini Model
              <select
                aria-label="Gemini Model"
                className="input mt-1 text-xs"
                value={geminiModelInput}
                onChange={(e) => setGeminiModelInput(e.target.value)}
              >
                {GEMINI_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="field-label">
              FRED API Key (Optional)
              <input
                type="password"
                aria-label="FRED API Key"
                placeholder={
                  configStatus?.fred_key_masked
                    ? `Current: ${configStatus.fred_key_masked}`
                    : 'Optional St. Louis Fed key'
                }
                className="input mt-1 font-mono text-xs"
                value={fredKeyInput}
                onChange={(e) => setFredKeyInput(e.target.value)}
                autoComplete="off"
              />
            </label>
          </div>

          <div className="mt-3 flex items-center justify-end gap-2">
            <button
              type="button"
              className="secondary-button"
              onClick={() => setShowConfigForm(false)}
            >
              Close
            </button>
            <button type="submit" className="primary-button" disabled={isSavingConfig}>
              {isSavingConfig ? (
                <LoaderCircle className="animate-spin" size={14} />
              ) : (
                <Check size={14} />
              )}
              Save & Apply
            </button>
          </div>
        </form>
      )}

      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        Ask in natural language to search DBnomics & SDMX, sync series into DuckDB, compute
        transformations, or run custom SQL queries.
      </p>

      <div className="mb-4 flex flex-wrap gap-2">
        {SUGGESTED_PROMPTS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            disabled={isSending}
            className="pill hover:border-amber-500/50 hover:text-amber-600 dark:hover:text-amber-400"
            onClick={() => void submitPrompt(suggestion)}
          >
            {suggestion.length > 78 ? `${suggestion.slice(0, 78)}…` : suggestion}
          </button>
        ))}
      </div>

      {error && (
        <div role="alert" className="alert mb-4">
          <AlertCircle className="mt-0.5 shrink-0 text-red-500" size={18} />
          <span className="flex-1">{error}</span>
        </div>
      )}

      {messages.length > 0 && (
        <div className="mb-4 max-h-96 space-y-3 overflow-y-auto rounded-xl border border-zinc-200/80 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-900/50">
          {messages.map((entry) => (
            <div
              key={entry.id}
              className={`rounded-lg p-3 text-sm ${
                entry.role === 'user'
                  ? 'ml-6 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
                  : 'mr-6 border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950'
              }`}
            >
              <div className="mb-1 flex items-center gap-1.5 text-xs font-medium opacity-75">
                {entry.role === 'assistant' && <Bot size={13} />}
                <span>{entry.role === 'user' ? 'You' : 'Gemini Economist'}</span>
              </div>
              {entry.toolCalls && entry.toolCalls.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {entry.toolCalls.map((tc, idx) => (
                    <span
                      key={`${tc.name}-${idx}`}
                      className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] text-amber-700 dark:text-amber-300"
                      title={tc.summary}
                    >
                      <Wrench size={11} />
                      {tc.name}: {tc.summary}
                    </span>
                  ))}
                </div>
              )}
              <p className="whitespace-pre-wrap leading-relaxed">{entry.text}</p>
            </div>
          ))}
        </div>
      )}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void submitPrompt(promptInput)
        }}
      >
        <input
          type="text"
          aria-label="Ask AI Economist Assistant"
          placeholder="e.g. Compare US and Euro Area CPI YoY inflation since 2020..."
          className="input flex-1"
          value={promptInput}
          onChange={(e) => setPromptInput(e.target.value)}
          disabled={isSending}
        />
        <button
          type="submit"
          className="primary-button shrink-0"
          disabled={isSending || !promptInput.trim()}
        >
          {isSending ? <LoaderCircle className="animate-spin" size={16} /> : <Send size={16} />}
          Ask AI
        </button>
      </form>
    </section>
  )
}
