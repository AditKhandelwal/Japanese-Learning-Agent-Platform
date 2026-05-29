import './KanaGuidePage.css'

interface Props {
  onBack: () => void
  onStartPractice: (mode: 'hiragana' | 'katakana') => void
}

type Cell = [string, string] | null  // [character, romaji]

const VOWEL_HEADERS = ['a', 'i', 'u', 'e', 'o']

const HIRA_ROWS: { label: string; cells: Cell[] }[] = [
  { label: '—', cells: [['あ','a'],  ['い','i'],  ['う','u'],   ['え','e'],  ['お','o']]  },
  { label: 'k',  cells: [['か','ka'], ['き','ki'], ['く','ku'],  ['け','ke'], ['こ','ko']] },
  { label: 's',  cells: [['さ','sa'], ['し','shi'],['す','su'],  ['せ','se'], ['そ','so']] },
  { label: 't',  cells: [['た','ta'], ['ち','chi'],['つ','tsu'], ['て','te'], ['と','to']] },
  { label: 'n',  cells: [['な','na'], ['に','ni'], ['ぬ','nu'],  ['ね','ne'], ['の','no']] },
  { label: 'h',  cells: [['は','ha'], ['ひ','hi'], ['ふ','fu'],  ['へ','he'], ['ほ','ho']] },
  { label: 'm',  cells: [['ま','ma'], ['み','mi'], ['む','mu'],  ['め','me'], ['も','mo']] },
  { label: 'y',  cells: [['や','ya'], null,        ['ゆ','yu'],  null,        ['よ','yo']] },
  { label: 'r',  cells: [['ら','ra'], ['り','ri'], ['る','ru'],  ['れ','re'], ['ろ','ro']] },
  { label: 'w',  cells: [['わ','wa'], null,        null,         null,        ['を','wo']] },
  { label: 'n',  cells: [['ん','n'],  null,        null,         null,        null]        },
]

const KATA_ROWS: { label: string; cells: Cell[] }[] = [
  { label: '—', cells: [['ア','a'],  ['イ','i'],  ['ウ','u'],   ['エ','e'],  ['オ','o']]  },
  { label: 'k',  cells: [['カ','ka'], ['キ','ki'], ['ク','ku'],  ['ケ','ke'], ['コ','ko']] },
  { label: 's',  cells: [['サ','sa'], ['シ','shi'],['ス','su'],  ['セ','se'], ['ソ','so']] },
  { label: 't',  cells: [['タ','ta'], ['チ','chi'],['ツ','tsu'], ['テ','te'], ['ト','to']] },
  { label: 'n',  cells: [['ナ','na'], ['ニ','ni'], ['ヌ','nu'],  ['ネ','ne'], ['ノ','no']] },
  { label: 'h',  cells: [['ハ','ha'], ['ヒ','hi'], ['フ','fu'],  ['ヘ','he'], ['ホ','ho']] },
  { label: 'm',  cells: [['マ','ma'], ['ミ','mi'], ['ム','mu'],  ['メ','me'], ['モ','mo']] },
  { label: 'y',  cells: [['ヤ','ya'], null,        ['ユ','yu'],  null,        ['ヨ','yo']] },
  { label: 'r',  cells: [['ラ','ra'], ['リ','ri'], ['ル','ru'],  ['レ','re'], ['ロ','ro']] },
  { label: 'w',  cells: [['ワ','wa'], null,        null,         null,        ['ヲ','wo']] },
  { label: 'n',  cells: [['ン','n'],  null,        null,         null,        null]        },
]

const TIPS = [
  {
    icon: '1',
    title: 'Learn the 5 vowels first',
    body: 'Every kana sound ends in one of five vowels: a, i, u, e, o. Nail these — あ い う え お — and every other row follows the same pattern.',
  },
  {
    icon: '2',
    title: 'Learn in rows, not randomly',
    body: 'All k-sounds (か き く け こ) follow the same pattern. Learn the consonant group together instead of jumping between characters.',
  },
  {
    icon: '3',
    title: 'Hiragana first, then katakana',
    body: 'Both alphabets represent the exact same 46 sounds. Master hiragana first — katakana will come faster because you already know the sounds.',
  },
  {
    icon: '4',
    title: 'Use mnemonics for tricky shapes',
    body: 'し looks like a fishhook (shi — "she"). ん is a backwards n. ツ and シ are often confused — ツ has strokes going up-right, シ has them going down-right.',
  },
  {
    icon: '5',
    title: 'Know when to use which',
    body: 'Hiragana is for native Japanese words and grammar (は, が, です). Katakana is for foreign loanwords — コーヒー (kōhī = coffee), テレビ (terebi = TV).',
  },
  {
    icon: '6',
    title: 'Repetition beats cramming',
    body: 'The flashcard practice modes use spaced repetition — characters you struggle with come back sooner. Short daily sessions beat one long grind.',
  },
]

function KanaChart({ rows, title, accent }: {
  rows: typeof HIRA_ROWS
  title: string
  accent: string
}) {
  return (
    <div className="kg-chart">
      <h3 className="kg-chart-title" style={{ color: accent }}>{title}</h3>
      <div className="kg-grid">
        {/* Column headers */}
        <div className="kg-cell kg-cell--corner" />
        {VOWEL_HEADERS.map(v => (
          <div key={v} className="kg-cell kg-cell--header">{v}</div>
        ))}
        {/* Rows */}
        {rows.map(({ label, cells }) => (
          <>
            <div key={`lbl-${label}`} className="kg-cell kg-cell--label">{label}</div>
            {cells.map((cell, i) =>
              cell ? (
                <div key={i} className="kg-cell kg-cell--char">
                  <span className="kg-kana">{cell[0]}</span>
                  <span className="kg-romaji">{cell[1]}</span>
                </div>
              ) : (
                <div key={i} className="kg-cell kg-cell--empty" />
              )
            )}
          </>
        ))}
      </div>
    </div>
  )
}

export default function KanaGuidePage({ onBack, onStartPractice }: Props) {
  return (
    <div className="kg-root">
      {/* Header */}
      <header className="kg-header">
        <div className="kg-logo">
          <span className="kg-logo-ja">先生AI</span>
          <span className="kg-logo-en">Japanese Tutor</span>
        </div>
        <div className="kg-title-badge">
          <span className="kg-title-kana">あア</span>
          <span className="kg-title-text">Kana Guide</span>
        </div>
        <button className="kg-back-btn" onClick={onBack}>← Dashboard</button>
      </header>

      <main className="kg-main">

        {/* Intro */}
        <section className="kg-section kg-intro">
          <h2 className="kg-section-title">What is kana?</h2>
          <p className="kg-intro-body">
            Japanese uses two phonetic alphabets — <strong>hiragana</strong> and <strong>katakana</strong> — alongside kanji. Unlike kanji, which carry meaning, every kana character represents a single <em>sound syllable</em>. Both alphabets cover the same 46 sounds.
          </p>
          <div className="kg-intro-cards">
            <div className="kg-intro-card kg-intro-card--hira">
              <div className="kg-intro-card-kana">ひらがな</div>
              <div className="kg-intro-card-name">Hiragana</div>
              <div className="kg-intro-card-desc">Rounded, cursive shapes. Used for native Japanese words, verb endings, and grammatical particles.</div>
              <div className="kg-intro-card-example">
                <span className="kg-example-word">たべる</span>
                <span className="kg-example-gloss">taberu — "to eat"</span>
              </div>
            </div>
            <div className="kg-intro-card kg-intro-card--kata">
              <div className="kg-intro-card-kana">カタカナ</div>
              <div className="kg-intro-card-name">Katakana</div>
              <div className="kg-intro-card-desc">Angular, sharp shapes. Used for foreign loanwords, emphasis, and technical terms.</div>
              <div className="kg-intro-card-example">
                <span className="kg-example-word">コーヒー</span>
                <span className="kg-example-gloss">kōhī — "coffee"</span>
              </div>
            </div>
          </div>
        </section>

        {/* Charts */}
        <section className="kg-section">
          <h2 className="kg-section-title">Character charts</h2>
          <p className="kg-section-sub">Hover over any cell to highlight it. Rows share a consonant; columns share a vowel.</p>
          <div className="kg-charts-grid">
            <KanaChart rows={HIRA_ROWS} title="Hiragana" accent="#48dbfb" />
            <KanaChart rows={KATA_ROWS} title="Katakana" accent="#1dd1a1" />
          </div>
        </section>

        {/* Tips */}
        <section className="kg-section">
          <h2 className="kg-section-title">Tips for learning</h2>
          <div className="kg-tips-grid">
            {TIPS.map(tip => (
              <div key={tip.icon} className="kg-tip">
                <div className="kg-tip-icon">{tip.icon}</div>
                <div>
                  <div className="kg-tip-title">{tip.title}</div>
                  <div className="kg-tip-body">{tip.body}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="kg-section kg-cta">
          <h2 className="kg-cta-title">Ready to practice?</h2>
          <p className="kg-cta-sub">The flashcard modes use spaced repetition — each character gets its own difficulty tracking.</p>
          <div className="kg-cta-btns">
            <button className="kg-cta-btn kg-cta-btn--hira" onClick={() => onStartPractice('hiragana')}>
              Practice Hiragana →
            </button>
            <button className="kg-cta-btn kg-cta-btn--kata" onClick={() => onStartPractice('katakana')}>
              Practice Katakana →
            </button>
          </div>
        </section>

      </main>
    </div>
  )
}
