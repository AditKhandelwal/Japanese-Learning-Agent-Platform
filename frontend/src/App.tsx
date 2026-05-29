import { useEffect, useState, useRef } from 'react'
import { supabase } from './lib/supabase'
import { getOrCreateMe, startSession } from './lib/api'
import type { Session } from '@supabase/supabase-js'
import LoginPage from './pages/LoginPage'
import OnboardingPage from './pages/OnboardingPage'
import DashboardPage from './pages/DashboardPage'
import SessionPage from './pages/SessionPage'
import RecallPage from './pages/RecallPage'
import KanaGuidePage from './pages/KanaGuidePage'
import ProgressPage from './pages/ProgressPage'

type AppState = 'loading' | 'login' | 'onboarding' | 'dashboard' | 'session' | 'kana-guide' | 'progress'

interface ActiveSession {
  sessionId: string
  userId: string
  mode: string
}

export default function App() {
  const [, setSession] = useState<Session | null>(null)
  const [appState, setAppState] = useState<AppState>('loading')
  const [activeSession, setActiveSession] = useState<ActiveSession | null>(null)
  const [currentUserId, setCurrentUserId] = useState<string>('')

  // Prevents the onAuthStateChange fired by signUp from advancing state.
  // LoginPage sets this before signup so we stay on the login page after account creation.
  const skipNextAuthEvent = useRef(false)

  async function loadUser(s: Session | null) {
    if (!s) { setAppState('login'); return }
    try {
      const user = await getOrCreateMe()
      setCurrentUserId(user.id)
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

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (skipNextAuthEvent.current) {
        skipNextAuthEvent.current = false
        return
      }
      if (event === 'SIGNED_IN') {
        setSession(session)
        loadUser(session)
      } else if (event === 'SIGNED_OUT') {
        setSession(null)
        setCurrentUserId('')
        setAppState('login')
      }
      // Ignore TOKEN_REFRESHED, INITIAL_SESSION, USER_UPDATED — don't reset app state
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

  async function handleKanaGuideStart(mode: 'hiragana' | 'katakana') {
    try {
      const user = await getOrCreateMe()
      const session = await startSession(user.id, mode)
      handleStartSession(mode, session.id, user.id)
    } catch {
      setAppState('dashboard')
    }
  }

  if (appState === 'loading') return null
  if (appState === 'login') return <LoginPage onSignUpComplete={() => { skipNextAuthEvent.current = true }} />
  if (appState === 'onboarding') return <OnboardingPage onComplete={() => setAppState('dashboard')} />
  if (appState === 'kana-guide') {
    return (
      <KanaGuidePage
        onBack={() => setAppState('dashboard')}
        onStartPractice={handleKanaGuideStart}
      />
    )
  }

  if (appState === 'progress') {
    return (
      <ProgressPage
        userId={currentUserId}
        onBack={() => setAppState('dashboard')}
      />
    )
  }

  if (appState === 'session' && activeSession) {
    if (['recall', 'kanji', 'hiragana', 'katakana'].includes(activeSession.mode)) {
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

  return <DashboardPage onStartSession={handleStartSession} onKanaGuide={() => setAppState('kana-guide')} onProgress={() => setAppState('progress')} />
}
