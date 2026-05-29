import { useEffect, useState, useCallback } from 'react'
import { getProgress, type ProgressItem, type LevelStat } from '../lib/api'
import './ProgressPage.css'

interface Props {
  userId: string
  onBack: () => void
}

type Tab = 'kana' | 'vocab' | 'kanji' | 'grammar'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'kana',    label: 'Kana',    icon: 'あア' },
  { id: 'vocab',   label: 'Vocab',   icon: '語'  },
  { id: 'kanji',   label: 'Kanji',   icon: '漢'  },
  { id: 'grammar', label: 'Grammar', icon: '文'  },
]

const LEVEL_ORDER = ['hiragana', 'katakana', 'N5', 'N4', 'N3', 'N2', 'N1']

const KANA_LEVELS = ['hiragana', 'katakana']
const JLPT_LEVELS = ['N5', 'N4', 'N3', 'N2', 'N1']

function masteryLabel(p: number): string {
  if (p >= 0.8) return 'mastered'
  if (p >= 0.5) return 'familiar'
  if (p >= 0.3) return 'learning'
  return 'weak'
}

function masteryColor(p: number): string {
  if (p >= 0.8) return '#1dd1a1'
  if (p >= 0.5) return '#48dbfb'
  if (p >= 0.3) return '#ff9f43'
  return '#ff4757'
}

function SummaryBar({ stats }: { stats: LevelStat }) {
  const total = stats.mastered + stats.familiar + stats.learning + stats.weak
  if (total === 0) return null
  const pct = (n: number) => `${Math.round((n / total) * 100)}%`
  return (
    <div className="pg-summary-bar">
      {stats.mastered > 0 && (
        <div className="pg-summary-seg" style={{ width: pct(stats.mastered), background: '#1dd1a1' }} title={`${stats.mastered} mastered`} />
      )}
      {stats.familiar > 0 && (
        <div className="pg-summary-seg" style={{ width: pct(stats.familiar), background: '#48dbfb' }} title={`${stats.familiar} familiar`} />
      )}
      {stats.learning > 0 && (
        <div className="pg-summary-seg" style={{ width: pct(stats.learning), background: '#ff9f43' }} title={`${stats.learning} learning`} />
      )}
      {stats.weak > 0 && (
        <div className="pg-summary-seg" style={{ width: pct(stats.weak), background: '#ff4757' }} title={`${stats.weak} weak`} />
      )}
    </div>
  )
}

function ItemRow({ item }: { item: ProgressItem }) {
  const color = masteryColor(item.p_know)
  const pct   = Math.round(item.p_know * 100)
  const showReading = item.reading && item.reading !== item.japanese && !/^[a-zA-Z]/.test(item.reading)
  return (
    <div className="pg-item-row">
      <div className="pg-item-left">
        <span className="pg-item-jp">{item.japanese}</span>
        {showReading && <span className="pg-item-reading">{item.reading}</span>}
        <span className="pg-item-meaning">{item.meaning}</span>
      </div>
      <div className="pg-item-right">
        <div className="pg-bar-track">
          <div className="pg-bar-fill" style={{ width: `${pct}%`, background: color }} />
        </div>
        <span className="pg-item-pct" style={{ color }}>{pct}%</span>
        <span className={`pg-mastery-badge pg-mastery-badge--${masteryLabel(item.p_know)}`}>
          {masteryLabel(item.p_know)}
        </span>
      </div>
    </div>
  )
}

export default function ProgressPage({ userId, onBack }: Props) {
  const [tab, setTab] = useState<Tab>('kana')
  const [level, setLevel] = useState<string | undefined>(undefined)
  const [items, setItems] = useState<ProgressItem[]>([])
  const [levelStats, setLevelStats] = useState<Record<string, LevelStat>>({})
  const [totalReviewed, setTotalReviewed] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const PER_PAGE = 50

  const levelOptions = tab === 'kana' ? KANA_LEVELS : JLPT_LEVELS

  const load = useCallback(async (newPage: number, reset: boolean) => {
    setLoading(true)
    try {
      const data = await getProgress({
        itemType: tab,
        jlptLevel: level,
        page: newPage,
        perPage: PER_PAGE,
      })
      setItems(prev => reset ? data.items : [...prev, ...data.items])
      setLevelStats(data.level_stats)
      setTotalReviewed(data.total_reviewed)
      setHasMore(data.items.length === PER_PAGE)
      setPage(newPage)
    } finally {
      setLoading(false)
    }
  }, [tab, level])

  useEffect(() => {
    setItems([])
    setPage(1)
    load(1, true)
  }, [tab, level, load])

  // Aggregate stats across all levels (or just selected level)
  const relevantLevels = level
    ? (levelStats[level] ? [levelStats[level]] : [])
    : levelOptions.map(l => levelStats[l]).filter(Boolean) as LevelStat[]

  const aggregate = relevantLevels.reduce(
    (acc, s) => ({
      mastered: acc.mastered + s.mastered,
      familiar: acc.familiar + s.familiar,
      learning: acc.learning + s.learning,
      weak:     acc.weak + s.weak,
      reviewed: acc.reviewed + s.reviewed,
      total_items: acc.total_items + (s.total_items ?? 0),
      avg_p_know: 0,
    }),
    { mastered: 0, familiar: 0, learning: 0, weak: 0, reviewed: 0, total_items: 0, avg_p_know: 0 }
  )

  return (
    <div className="pg-root">
      {/* Header */}
      <header className="pg-header">
        <div className="pg-logo">
          <span className="pg-logo-ja">先生AI</span>
          <span className="pg-logo-en">Japanese Tutor</span>
        </div>
        <div className="pg-title-badge">
          <span className="pg-title-icon">📊</span>
          <span className="pg-title-text">Progress</span>
        </div>
        <button className="pg-back-btn" onClick={onBack}>← Dashboard</button>
      </header>

      {/* Tabs */}
      <div className="pg-tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`pg-tab ${tab === t.id ? 'pg-tab--active' : ''}`}
            onClick={() => { setTab(t.id); setLevel(undefined) }}
          >
            <span className="pg-tab-icon">{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      <main className="pg-main">
        {/* Level filter */}
        <div className="pg-level-filter">
          <button
            className={`pg-level-btn ${!level ? 'pg-level-btn--active' : ''}`}
            onClick={() => setLevel(undefined)}
          >
            All
          </button>
          {levelOptions.map(l => {
            const s = levelStats[l]
            return (
              <button
                key={l}
                className={`pg-level-btn ${level === l ? 'pg-level-btn--active' : ''}`}
                onClick={() => setLevel(l)}
              >
                {l.charAt(0).toUpperCase() + l.slice(1)}
                {s && s.reviewed > 0 && (
                  <span className="pg-level-count">{s.reviewed}</span>
                )}
              </button>
            )
          })}
        </div>

        {/* Aggregate summary */}
        {aggregate.reviewed > 0 && (
          <div className="pg-agg-summary">
            <SummaryBar stats={aggregate} />
            <div className="pg-agg-counts">
              <span className="pg-agg-reviewed">
                <strong>{aggregate.reviewed}</strong> reviewed
                {aggregate.total_items > 0 && (
                  <span className="pg-agg-total"> / {aggregate.total_items} total</span>
                )}
              </span>
              <div className="pg-agg-legend">
                {aggregate.mastered > 0 && <span style={{ color: '#1dd1a1' }}>●&nbsp;{aggregate.mastered} mastered</span>}
                {aggregate.familiar > 0 && <span style={{ color: '#48dbfb' }}>●&nbsp;{aggregate.familiar} familiar</span>}
                {aggregate.learning > 0 && <span style={{ color: '#ff9f43' }}>●&nbsp;{aggregate.learning} learning</span>}
                {aggregate.weak     > 0 && <span style={{ color: '#ff4757' }}>●&nbsp;{aggregate.weak} weak</span>}
              </div>
            </div>
          </div>
        )}

        {/* Item list */}
        {loading && items.length === 0 ? (
          <div className="pg-loading"><div className="pg-spinner" /></div>
        ) : items.length === 0 ? (
          <div className="pg-empty">
            <span className="pg-empty-icon">📭</span>
            <p>No {tab === 'kana' ? 'kana' : 'reviewed'} items yet{level ? ` at ${level}` : ''}.</p>
            <p className="pg-empty-sub">Start a practice session to track your progress here.</p>
          </div>
        ) : (
          <>
            {/* Group by level when showing all */}
            {!level
              ? LEVEL_ORDER.filter(l => levelOptions.includes(l)).map(l => {
                  const levelItems = items.filter(i => i.jlpt_level === l)
                  if (levelItems.length === 0) return null
                  const s = levelStats[l]
                  return (
                    <div key={l} className="pg-level-section">
                      <div className="pg-level-header">
                        <span className="pg-level-label">{l.charAt(0).toUpperCase() + l.slice(1)}</span>
                        {s && <SummaryBar stats={s} />}
                        {s && <span className="pg-level-stat">{s.reviewed} reviewed</span>}
                      </div>
                      {levelItems.map(item => <ItemRow key={item.item_id} item={item} />)}
                    </div>
                  )
                })
              : items.map(item => <ItemRow key={item.item_id} item={item} />)
            }

            {hasMore && (
              <button
                className="pg-load-more"
                onClick={() => load(page + 1, false)}
                disabled={loading}
              >
                {loading ? 'Loading…' : 'Load more'}
              </button>
            )}
          </>
        )}
      </main>
    </div>
  )
}
