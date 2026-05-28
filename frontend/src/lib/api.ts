import { supabase } from './supabase'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token ?? ''}`,
  }
}

export interface ChatEvent {
  type: 'text' | 'tool_call' | 'tool_result' | 'done'
  content?: string
  name?: string
  input?: Record<string, unknown>
  result?: unknown
}

export async function streamChat(
  params: { userId: string; sessionId: string; mode: string; message: string },
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const headers = await authHeaders()
  const res = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      user_id: params.userId,
      session_id: params.sessionId,
      mode: params.mode,
      message: params.message,
    }),
  })
  if (!res.ok || !res.body) throw new Error('Chat request failed')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)
        if (data === '[DONE]') return
        try {
          onEvent(JSON.parse(data) as ChatEvent)
        } catch {
          // skip malformed chunk
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}

export async function getOrCreateMe() {
  const res = await fetch(`${API_URL}/api/users/me`, {
    headers: await authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to get user')
  return res.json()
}

export async function completeOnboarding(data: {
  prior_study: string
  knows_hiragana: string
  knows_katakana: string
  kanji_level: string
  jlpt_self_assessment: string
  study_frequency: string
}) {
  const res = await fetch(`${API_URL}/api/users/me/onboarding`, {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to complete onboarding')
  return res.json()
}

export async function startSession(userId: string, mode: string) {
  const res = await fetch(`${API_URL}/api/sessions/`, {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({ user_id: userId, mode }),
  })
  if (!res.ok) throw new Error('Failed to start session')
  return res.json() as Promise<{ id: string; user_id: string; mode: string; started_at: string }>
}

export interface RecallItem {
  item_id: string
  japanese: string
  reading: string | null
  meaning: string
  type: string
  jlpt_level: string
  p_know: number
  priority_score: number
  review_count: number
}

export interface RecallQueueOptions {
  n?: number
  excludeKana?: boolean
  jlptLevel?: string
  ignoreDue?: boolean
}

export async function getRecallQueue(
  userId: string,
  options: RecallQueueOptions = {},
): Promise<{ items: RecallItem[]; total_due: number }> {
  const headers = await authHeaders()
  const params = new URLSearchParams({ user_id: userId })
  if (options.n)          params.set('n',            String(options.n))
  if (options.excludeKana) params.set('exclude_kana', 'true')
  if (options.jlptLevel)  params.set('jlpt_level',   options.jlptLevel)
  if (options.ignoreDue)  params.set('ignore_due',   'true')
  const res = await fetch(`${API_URL}/api/sessions/queue?${params}`, { headers })
  if (!res.ok) throw new Error('Failed to fetch recall queue')
  return res.json()
}

export type SRSRating = 'again' | 'hard' | 'good' | 'easy'

export interface RateResult {
  item_id: string
  rating: SRSRating
  correct: boolean
  p_know_before: number
  p_know_after: number
  next_review_due: string
}

export async function rateItem(params: {
  sessionId: string
  userId: string
  itemId: string
  rating: SRSRating
}): Promise<RateResult> {
  const res = await fetch(`${API_URL}/api/sessions/rate`, {
    method: 'POST',
    headers: await authHeaders(),
    body: JSON.stringify({
      session_id: params.sessionId,
      user_id: params.userId,
      item_id: params.itemId,
      rating: params.rating,
    }),
  })
  if (!res.ok) throw new Error('Failed to rate item')
  return res.json()
}