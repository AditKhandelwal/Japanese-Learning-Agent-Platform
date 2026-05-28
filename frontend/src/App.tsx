import { useEffect, useState, useRef } from 'react'
import { supabase } from './lib/supabase'
import { getOrCreateMe } from './lib/api'
import type { Session } from '@supabase/supabase-js'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import DashboardPage from './pages/DashboardPage'
import SessionPage from './pages/SessionPage'
import RecallPage from './pages/RecallPage'

type AppState = 'loading' | 'login' | 'onboarding' | 'dashboard' | 'session' | 'kana-guide'

interface ActiveSession {
  sessionId: string
  userId: string
  mode: string
}

export default function App() {
  const [, setSession] = useState<Session | null>(null)
  const [appState, setAppState] = useState<AppState>('loading')
  const [activeSession, setActiveSession] = useState<ActiveSession | null>(null)

  // Prevents the onAuthStateChange fired by signUp from advancing state.
  // LoginPage sets this before signup so we stay on the login page after account creation.
  const skipNextAuthEvent = useRef(false)

  async function loadUser(s: Session | null) {
    if (!s) { setAppState('login'); return }
    try {
      const user = await getOrCreateMe()
      setAppState(user.onboarding_done ? 'dashboard' : 'onboarding')
    } catch {
      setAppState('login')
    }
  }

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      loadUser(session)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (skipNextAuthEvent.current) {
        skipNextAuthEvent.current = false
        return
      }
      setSession(session)
      loadUser(session)
    })

    return () => subscription.unsubscribe()
  }, [])

  function handleStartSession(mode: string, sessionId: string, userId: string) {
    setActiveSession({ mode, sessionId, userId })
    setAppState('session')
  }

  function handleEndSession() {
    setActiveSession(null)
    setAppState('dashboard')
  }

  if (appState === 'loading') return null
  if (appState === 'login') return <LoginPage onSignUpComplete={() => { skipNextAuthEvent.current = true }} />
  if (appState === 'onboarding') return <OnboardingPage onComplete={() => setAppState('dashboard')} />
  if (appState === 'kana-guide') {
    return (
      <div style={{ minHeight: '100vh', background: '#0a0a14', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#fff', fontFamily: 'Segoe UI, system-ui, sans-serif', gap: 16 }}>
        <p style={{ fontSize: '3rem', fontFamily: 'MS Gothic, monospace' }}>あア</p>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Kana Guide — Coming Soon</h1>
        <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.9rem' }}>Full guide with charts and tips is being built.</p>
        <button onClick={() => setAppState('dashboard')} style={{ marginTop: 8, padding: '10px 28px', background: 'linear-gradient(135deg,#48dbfb,#1dd1a1)', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 700, cursor: 'pointer' }}>Back to Dashboard</button>
      </div>
    )
  }

  if (appState === 'session' && activeSession) {
    if (['recall', 'hiragana', 'katakana'].includes(activeSession.mode)) {
      return (
        <RecallPage
          sessionId={activeSession.sessionId}
          userId={activeSession.userId}
          mode={activeSession.mode}
          onEnd={handleEndSession}
        />
      )
    }
    return (
      <SessionPage
        sessionId={activeSession.sessionId}
        userId={activeSession.userId}
        mode={activeSession.mode}
        onEnd={handleEndSession}
      />
    )
  }

  return <DashboardPage onStartSession={handleStartSession} onKanaGuide={() => setAppState('kana-guide')} />
}
