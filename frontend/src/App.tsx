import { useEffect, useState, useRef } from 'react'
import { supabase } from './lib/supabase'
import { getOrCreateMe } from './lib/api'
import type { Session } from '@supabase/supabase-js'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import DashboardPage from './pages/DashboardPage'

type AppState = 'loading' | 'login' | 'onboarding' | 'dashboard' | 'session'

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
  if (appState === 'session' && activeSession) {
    return (
      <div style={{ minHeight: '100vh', background: '#0a0a14', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16, fontFamily: 'Segoe UI, system-ui, sans-serif' }}>
        <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem' }}>
          {activeSession.mode} session · {activeSession.sessionId}
        </p>
        <button
          onClick={handleEndSession}
          style={{ background: 'none', border: '1px solid rgba(255,107,157,0.4)', borderRadius: 8, color: '#ff6b9d', padding: '8px 20px', cursor: 'pointer', fontSize: '0.9rem' }}
        >
          ← Back to dashboard
        </button>
      </div>
    )
  }

  return <DashboardPage onStartSession={handleStartSession} />
}
