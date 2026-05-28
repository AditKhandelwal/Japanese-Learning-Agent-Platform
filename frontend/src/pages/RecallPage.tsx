import { useEffect, useState, useRef } from 'react'
import { getRecallQueue, rateItem } from '../lib/api'
import type { RecallItem, SRSRating } from '../lib/api'
import './RecallPage.css'

interface Props {
  sessionId: string
  userId: string
  mode: string  // 'recall' | 'hiragana' | 'katakana'
  onEnd: () => void
}

type CardState = 'loading' | 'front' | 'revealed' | 'empty'

interface SessionStats {
  done: number
  correct: number
  again: number
}

const MODE_META: Record<string, { kanji: string; name: string }> = {
  recall:   { kanji: '復', name: 'Vocab Recall' },
  hiragana: { kanji: 'ひ', name: 'Hiragana' },
  katakana: { kanji: 'カ', name: 'Katakana' },
}

export default function RecallPage({ sessionId, userId, mode, onEnd }: Props) {
  const [cards, setCards] = useState<RecallItem[]>([])
  const [totalDue, setTotalDue] = useState(0)
  const [cardState, setCardState] = useState<CardState>('loading')
  const [stats, setStats] = useState<SessionStats>({ done: 0, correct: 0, again: 0 })
  const [lap, setLap] = useState(1)
  const [showLapBanner, setShowLapBanner] = useState(false)
  const cardStartRef = useRef<number>(Date.now())

  const isKana = mode === 'hiragana' || mode === 'katakana'
  const meta = MODE_META[mode] ?? MODE_META.recall

  useEffect(() => {
    loadQueue()
  }, [])

  async function loadQueue(drill = false) {
    setCardState('loading')
    try {
      const { items, total_due } = await getRecallQueue(userId, isKana ? {
        jlptLevel: mode,
        ignoreDue: drill,
        n: 60,
      } : {
        excludeKana: true,
        n: 20,
      })
      setTotalDue(total_due)
      if (items.length === 0) {
        setCardState('empty')
      } else {
        setCards(items)
        cardStartRef.current = Date.now()
        setCardState('front')
      }
    } catch {
      setCardState('empty')
    }
  }

  function reveal() {
    if (cardState === 'front') setCardState('revealed')
  }

  function rate(rating: SRSRating) {
    if (cardState !== 'revealed' || cards.length === 0) return
    const current = cards[0]

    // Fire BKT update in background — don't block the card advance
    rateItem({ sessionId, userId, itemId: current.item_id, rating }).catch(() => {})

    const isCorrect = rating !== 'again'
    setStats(s => ({
      done: s.done + 1,
      correct: s.correct + (isCorrect ? 1 : 0),
      again: s.again + (rating === 'again' ? 1 : 0),
    }))

    const nextCards = rating === 'again'
      ? [...cards.slice(1), current]
      : cards.slice(1)

    // Batch both updates so there's no intermediate render showing the
    // next card's back face
    setCards(nextCards)
    if (nextCards.length === 0) {
      setCardState('empty')
    } else {
      cardStartRef.current = Date.now()
      setCardState('front')
    }
  }

  const current = cards[0] ?? null
  const readingIsKana = current ? /[぀-ヿ]/.test(current.reading ?? '') : false
  const progressPct = isKana
    ? ((stats.done % (totalDue || 1)) / (totalDue || 1)) * 100
    : totalDue > 0 ? (stats.done / (totalDue + stats.again)) * 100 : 0

  return (
    <div className="recall-root">
      {/* Header */}
      <header className="recall-header">
        <div className="recall-logo">
          <span className="recall-logo-ja">学ぶ</span>
          <span className="recall-logo-en">Japanese</span>
        </div>

        <div className="recall-mode-badge">
          <span className="recall-mode-kanji">{meta.kanji}</span>
          <span className="recall-mode-name">{meta.name}</span>
          {isKana && lap > 1 && (
            <span className="recall-lap-badge">Lap {lap}</span>
          )}
        </div>

        <button className="recall-end-btn" onClick={onEnd}>End Session</button>
      </header>

      {/* Progress bar */}
      <div className="recall-progress-bar">
        <div className="recall-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>

      {/* Lap banner overlay */}
      {showLapBanner && (
        <div className="recall-lap-overlay">
          <div className="recall-lap-banner">
            <span className="recall-lap-kanji">完</span>
            <p className="recall-lap-text">Lap {lap - 1} complete!</p>
            <p className="recall-lap-sub">Starting lap {lap}…</p>
          </div>
        </div>
      )}

      {/* Loading */}
      {cardState === 'loading' && !showLapBanner && (
        <div className="recall-center">
          <div className="recall-spinner" />
        </div>
      )}

      {/* Empty / Done */}
      {cardState === 'empty' && (
        <div className="recall-center">
          <span className="recall-empty-kanji">完</span>
          <p className="recall-empty-title">
            {stats.done === 0 ? 'Nothing due right now' : 'All done for now!'}
          </p>
          <p className="recall-empty-sub">
            {stats.done === 0
              ? 'All your characters are up to date. Come back later when more are due.'
              : `You reviewed ${stats.done} card${stats.done !== 1 ? 's' : ''} — ${stats.correct} correct, ${stats.again} again.`}
          </p>
          {isKana && (
            <button className="recall-done-btn" style={{ marginBottom: 8 }} onClick={() => { setLap(l => l + 1); loadQueue(true) }}>
              Keep drilling →
            </button>
          )}
          <button className="recall-done-btn" style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)' }} onClick={onEnd}>
            Back to Dashboard
          </button>
        </div>
      )}

      {/* Active card */}
      {(cardState === 'front' || cardState === 'revealed') && current && (
        <div className="recall-main">
          <div className="recall-stats">
            <div className="recall-stat-item">
              <div className="recall-stat-dot" style={{ background: '#1dd1a1' }} />
              <span>{stats.correct} correct</span>
            </div>
            <div className="recall-stat-item">
              <div className="recall-stat-dot" style={{ background: '#ff4757' }} />
              <span>{stats.again} again</span>
            </div>
            <div className="recall-stat-item">
              <span>{cards.length} remaining</span>
            </div>
          </div>

          <div className="recall-card-wrap">
            <div
              className={`recall-card ${cardState !== 'front' ? 'recall-card--revealed' : ''}`}
              onClick={cardState === 'front' ? reveal : undefined}
            >
              {/* Front face */}
              <div className="recall-card-face">
                <span className="recall-card-type">{current.type}</span>
                <span className="recall-card-jlpt">{current.jlpt_level}</span>
                {readingIsKana ? (
                  <>
                    <div className="recall-card-japanese">{current.reading}</div>
                    <div className="recall-card-kanji-sub">{current.japanese}</div>
                  </>
                ) : (
                  <div className="recall-card-japanese">{current.japanese}</div>
                )}
                <div className="recall-card-hint">tap to reveal</div>
                <div className="recall-card-p-know">p={current.p_know.toFixed(2)}</div>
              </div>

              {/* Back face */}
              <div className="recall-card-face recall-card-back">
                <span className="recall-card-type">{current.type}</span>
                <span className="recall-card-jlpt">{current.jlpt_level}</span>
                <div className="recall-card-japanese--sm">{current.japanese}</div>
                {current.reading && current.reading !== current.japanese && (
                  <div className="recall-card-reading">{current.reading}</div>
                )}
                <div className="recall-divider" />
                <div className="recall-card-meaning">{current.meaning}</div>
                <div className="recall-card-p-know">p={current.p_know.toFixed(2)}</div>
              </div>
            </div>
          </div>

          {cardState === 'front' && (
            <button className="recall-reveal-btn" onClick={reveal}>Show Answer</button>
          )}

          {cardState === 'revealed' && (
            <div className="recall-ratings">
              {(
                [
                  { rating: 'again', label: 'Again', sub: '<1 min' },
                  { rating: 'hard',  label: 'Hard',  sub: '<10 min' },
                  { rating: 'good',  label: 'Good',  sub: '1 day' },
                  { rating: 'easy',  label: 'Easy',  sub: '4 days' },
                ] as const
              ).map(({ rating, label, sub }) => (
                <button
                  key={rating}
                  className={`recall-rating-btn recall-rating-btn--${rating}`}
                  onClick={() => rate(rating)}
                  disabled={cardState !== 'revealed'}
                >
                  <span className="recall-rating-label">{label}</span>
                  <span className="recall-rating-sub">{sub}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
