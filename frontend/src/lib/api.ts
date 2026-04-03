import { supabase } from './supabase'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

async function authHeaders() {
  const { data: { session } } = await supabase.auth.getSession()
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session?.access_token ?? ''}`,
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