import { useEffect, useState, type CSSProperties } from 'react'
import { supabase } from '../lib/supabase'
import { getOrCreateMe, startSession } from '../lib/api'
import './DashboardPage.css'

interface Props {
  onStartSession: (mode: string, sessionId: string, userId: string) => void
}

interface UserInfo {
  id: string
  username: string
  placement_level: string | null
}

const MODES = [
  {
    id: 'lesson',
    kanji: '学',
    name: 'Lesson',
    description: 'Learn new vocabulary, kanji, and grammar. Claude introduces items and adds them to your review queue.',
    gradient: 'linear-gradient(135deg, #ff6b9d, #ff9f43)',
    glow: 'rgba(255, 107, 157, 0.2)',
    border: 'rgba(255, 107, 157, 0.3)',
    featured: true,
  },
  {
    id: 'recall',
    kanji: '復',
    name: 'Recall',
    description: 'Flashcard-style review of items due for practice, ranked by your knowledge gaps.',
    gradient: 'linear-gradient(135deg, #ff9f43, #e056fd)',
    glow: 'rgba(255, 159, 67, 0.2)',
    border: 'rgba(255, 159, 67, 0.3)',
    featured: true,
  },
  {
    id: 'reading',
    kanji: '読',
    name: 'Reading',
    description: 'Short passages built from your known vocabulary with comprehension questions.',
    gradient: 'linear-gradient(135deg, #e056fd, #48dbfb)',
    glow: 'rgba(224, 86, 253, 0.15)',
    border: 'rgba(224, 86, 253, 0.25)',
    featured: false,
  },
  {
    id: 'production',
    kanji: '書',
    name: 'Production',
    description: 'Write sentences using target words or grammar points. Claude evaluates your output.',
    gradient: 'linear-gradient(135deg, #48dbfb, #1dd1a1)',
    glow: 'rgba(72, 219, 251, 0.15)',
    border: 'rgba(72, 219, 251, 0.25)',
    featured: false,
  },
  {
    id: 'conversation',
    kanji: '話',
    name: 'Conversation',
    description: 'Role-play a scenario in Japanese appropriate to your level.',
    gradient: 'linear-gradient(135deg, #1dd1a1, #ff6b9d)',
    glow: 'rgba(29, 209, 161, 0.15)',
    border: 'rgba(29, 209, 161, 0.25)',
    featured: false,
  },
]

function getGreeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function DashboardPage({ onStartSession }: Props) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [starting, setStarting] = useState<string | null>(null)

  useEffect(() => {
    getOrCreateMe().then(setUser).catch(() => {})
  }, [])

  async function handleStart(modeId: string) {
    if (!user || starting) return
    setStarting(modeId)
    try {
      const session = await startSession(user.id, modeId)
      onStartSession(modeId, session.id, user.id)
    } catch {
      setStarting(null)
    }
  }

  async function handleSignOut() {
    await supabase.auth.signOut()
  }

  const featured = MODES.filter(m => m.featured)
  const secondary = MODES.filter(m => !m.featured)

  return (
    <div className="dash-root">
      {/* Header */}
      <header className="dash-header">
        <div className="dash-logo">
          <span className="dash-logo-ja">先生AI</span>
          <span className="dash-logo-en">Japanese Tutor</span>
        </div>
        <div className="dash-header-right">
          {user && (
            <span className="dash-username">
              {user.placement_level
                ? `${user.username} · ${user.placement_level.toUpperCase()}`
                : user.username}
            </span>
          )}
          <button className="dash-signout" onClick={handleSignOut}>Sign out</button>
        </div>
      </header>

      {/* Body */}
      <main className="dash-main">
        <div className="dash-welcome">
          <h1 className="dash-greeting">
            {getGreeting()}{user ? `, ${user.username}` : ''}.
          </h1>
          <p className="dash-subtext">What would you like to practice today?</p>
        </div>

        {/* Featured modes: Lesson + Recall */}
        <div className="dash-featured-grid">
          {featured.map(mode => (
            <div
              key={mode.id}
              className="dash-card dash-card--featured"
              style={{
                '--glow': mode.glow,
                '--border': mode.border,
              } as CSSProperties}
            >
              <div className="dash-card-kanji" style={{ background: mode.gradient, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
                {mode.kanji}
              </div>
              <div className="dash-card-body">
                <h2 className="dash-card-name">{mode.name}</h2>
                <p className="dash-card-desc">{mode.description}</p>
              </div>
              <button
                className="dash-start-btn"
                style={{ background: mode.gradient }}
                onClick={() => handleStart(mode.id)}
                disabled={!!starting}
              >
                {starting === mode.id ? 'Starting…' : 'Begin →'}
              </button>
            </div>
          ))}
        </div>

        {/* Secondary modes */}
        <div className="dash-secondary-grid">
          {secondary.map(mode => (
            <div
              key={mode.id}
              className="dash-card dash-card--secondary"
              style={{
                '--glow': mode.glow,
                '--border': mode.border,
              } as CSSProperties}
            >
              <div className="dash-card-kanji dash-card-kanji--sm" style={{ background: mode.gradient, WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
                {mode.kanji}
              </div>
              <h2 className="dash-card-name">{mode.name}</h2>
              <p className="dash-card-desc">{mode.description}</p>
              <button
                className="dash-start-btn dash-start-btn--outline"
                style={{ '--btn-gradient': mode.gradient } as CSSProperties}
                onClick={() => handleStart(mode.id)}
                disabled={!!starting}
              >
                {starting === mode.id ? 'Starting…' : 'Begin →'}
              </button>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}