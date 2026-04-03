import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'
import './LoginPage.css'

const KANA = 'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン日本語学習漢字'.split('')

function useMatrixColumns(count: number) {
  const [columns, setColumns] = useState<{ chars: string[]; y: number; speed: number; x: number; opacity: number }[]>([])

  useEffect(() => {
    const cols = Array.from({ length: count }, (_, i) => ({
      chars: Array.from({ length: 20 }, () => KANA[Math.floor(Math.random() * KANA.length)]),
      y: Math.random() * -500,
      speed: 0.4 + Math.random() * 1.2,
      x: (i / count) * 100,
      opacity: 0.15 + Math.random() * 0.25,
    }))
    setColumns(cols)

    let frame: number
    const tick = () => {
      setColumns(prev => prev.map(col => {
        const newY = col.y + col.speed
        const reset = newY > 110
        return {
          ...col,
          y: reset ? -30 - Math.random() * 40 : newY,
          chars: reset
            ? Array.from({ length: 20 }, () => KANA[Math.floor(Math.random() * KANA.length)])
            : col.chars.map((c, i) => i === 0 && Math.random() < 0.05 ? KANA[Math.floor(Math.random() * KANA.length)] : c),
        }
      }))
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [count])

  return columns
}

interface Props {
  onSignUpComplete: () => void
}

export default function LoginPage({ onSignUpComplete }: Props) {
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSignUp, setIsSignUp] = useState(false)
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const columns = useMatrixColumns(18)

  async function handleSubmit(e: React.SyntheticEvent) {
    e.preventDefault()
    setError('')
    setInfo('')
    if (isSignUp && !username.trim()) {
      setError('Please enter a username.')
      return
    }
    if (isSignUp && password.length < 6) {
      setError('Password must be at least 6 characters.')
      return
    }
    if (isSignUp && password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    if (isSignUp) {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { username: username.trim() } },
      })
      if (error) {
        setError(error.message)
      } else if (!data.user) {
        setError('Sign up failed. Please try again.')
      } else {
        onSignUpComplete()  // tell App to skip the next onAuthStateChange event
        await supabase.auth.signOut()
        setIsSignUp(false)
        setPassword('')
        setConfirmPassword('')
        setUsername('')
        setInfo('Account created! Please sign in.')
      }
    } else {
      const { error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) {
        if (error.message.toLowerCase().includes('not confirmed') || error.message.toLowerCase().includes('email'))
          setError('Please confirm your email before signing in, or disable email confirmation in Supabase.')
        else
          setError(error.message)
      }
    }
    setLoading(false)
  }

  return (
    <div className="login-root">
      {/* Animated background */}
      <div className="matrix-bg" aria-hidden="true">
        {columns.map((col, i) => (
          <div
            key={i}
            className="matrix-col"
            style={{ left: `${col.x}%`, top: `${col.y}%`, opacity: col.opacity }}
          >
            {col.chars.map((c, j) => (
              <span key={j} style={{ color: j === 0 ? '#ff6b9d' : j < 3 ? '#ff9f43' : '#e056fd' }}>
                {c}
              </span>
            ))}
          </div>
        ))}
      </div>

      {/* Card */}
      <div className="login-card">
        <div className="login-logo">
          <span className="login-logo-ja">日本語</span>
          <span className="login-logo-en">Nihongo</span>
        </div>

        <h2 className="login-title">{isSignUp ? 'Create Account' : 'Welcome Back'}</h2>
        <p className="login-subtitle">{isSignUp ? 'Start your Japanese journey' : 'Continue your journey'}</p>

        <form onSubmit={handleSubmit} className="login-form">
          {isSignUp && (
            <div className="field">
              <label>Username</label>
              <input
                type="text"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="your_username"
                required
              />
            </div>
          )}

          <div className="field">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
          </div>

          <div className="field">
            <label>Password</label>
            <div className="field-input-wrap">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
              <button type="button" className="field-eye" onClick={() => setShowPassword(v => !v)}>
                {showPassword ? '🙈' : '👁️'}
              </button>
            </div>
          </div>

          {isSignUp && (
            <div className="field">
              <label>Confirm Password</label>
              <div className="field-input-wrap">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={e => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>
          )}

          {error && <p className="login-error">{error}</p>}
          {info && <p className="login-info">{info}</p>}

          <button type="submit" disabled={loading} className="login-btn">
            {loading ? '...' : isSignUp ? 'Sign Up' : 'Sign In'}
          </button>
        </form>

        <p className="login-switch">
          {isSignUp ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={() => { setIsSignUp(!isSignUp); setError(''); setInfo(''); setConfirmPassword(''); setUsername('') }} className="login-switch-btn">
            {isSignUp ? 'Sign In' : 'Sign Up'}
          </button>
        </p>
      </div>
    </div>
  )
}