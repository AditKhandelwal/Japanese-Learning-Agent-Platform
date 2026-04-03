import { useState } from 'react'
import { completeOnboarding } from '../lib/api'
import './OnboardingPage.css'

interface OnboardingAnswers {
  prior_study: string
  knows_hiragana: string
  knows_katakana: string
  kanji_level: string
  jlpt_self_assessment: string
  study_frequency: string
}

const QUESTIONS = [
  {
    id: 'prior_study',
    question: 'Have you studied Japanese before?',
    options: [
      { value: 'never',    label: 'Never',      sub: "I'm starting from scratch" },
      { value: 'some',     label: 'A little',   sub: 'Tried a few times' },
      { value: 'casual',   label: 'Casually',   sub: 'On and off for a while' },
      { value: 'serious',  label: 'Seriously',  sub: 'Dedicated study over months/years' },
    ],
  },
  {
    id: 'knows_hiragana',
    question: 'Can you read hiragana?',
    examples: 'あ い う え お か き く け こ',
    options: [
      { value: 'no',       label: 'No',        sub: "I can't read it yet" },
      { value: 'a_little', label: 'A little',  sub: 'I know some characters' },
      { value: 'yes',      label: 'Yes',       sub: 'I can read hiragana' },
    ],
  },
  {
    id: 'knows_katakana',
    question: 'Can you read katakana?',
    examples: 'ア イ ウ エ オ カ キ ク ケ コ',
    options: [
      { value: 'no',       label: 'No',        sub: "I can't read it yet" },
      { value: 'a_little', label: 'A little',  sub: 'I know some characters' },
      { value: 'yes',      label: 'Yes',       sub: 'I can read katakana' },
    ],
  },
  {
    id: 'kanji_level',
    question: 'How many kanji do you know?',
    examples: '日 本 語 学 習 漢 字 人 大 小',
    options: [
      { value: 'none', label: 'None',   sub: "I don't know any kanji" },
      { value: 'few',  label: 'A few',  sub: 'Less than 50' },
      { value: 'n5',   label: '~100',   sub: 'JLPT N5 level' },
      { value: 'n4',   label: '~300',   sub: 'JLPT N4 level' },
      { value: 'n3',   label: '~650',   sub: 'JLPT N3 level' },
      { value: 'n2',   label: '~1000',  sub: 'JLPT N2 level' },
      { value: 'n1',   label: '2000+',  sub: 'JLPT N1 level' },
    ],
  },
  {
    id: 'jlpt_self_assessment',
    question: 'If you know it — which JLPT level are you?',
    options: [
      { value: 'unsure', label: 'Not sure', sub: "I don't know about JLPT" },
      { value: 'n5',     label: 'N5',       sub: 'Beginner' },
      { value: 'n4',     label: 'N4',       sub: 'Elementary' },
      { value: 'n3',     label: 'N3',       sub: 'Intermediate' },
      { value: 'n2',     label: 'N2',       sub: 'Upper intermediate' },
      { value: 'n1',     label: 'N1',       sub: 'Advanced' },
    ],
  },
  {
    id: 'study_frequency',
    question: 'How much time do you want to study each day?',
    options: [
      { value: 'casual',    label: 'Casual',    sub: '5–10 min/day' },
      { value: 'regular',   label: 'Regular',   sub: '15–20 min/day' },
      { value: 'serious',   label: 'Serious',   sub: '30 min/day' },
      { value: 'intensive', label: 'Intensive', sub: '1+ hour/day' },
    ],
  },
]

function getLabel(questionId: string, value: string): string {
  const q = QUESTIONS.find(q => q.id === questionId)
  return q?.options.find(o => o.value === value)?.label ?? value
}

interface Props {
  onComplete: () => void
}

export default function OnboardingPage({ onComplete }: Props) {
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Partial<OnboardingAnswers>>({})
  const [confirming, setConfirming] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const q = QUESTIONS[step]
  const progress = confirming ? 100 : ((step) / QUESTIONS.length) * 100

  function select(value: string) {
    const updated = { ...answers, [q.id]: value }
    setAnswers(updated)

    if (step < QUESTIONS.length - 1) {
      setTimeout(() => setStep(s => s + 1), 200)
    } else {
      setTimeout(() => setConfirming(true), 200)
    }
  }

  async function submit() {
    setSubmitting(true)
    setError('')
    try {
      await completeOnboarding(answers as OnboardingAnswers)
      onComplete()
    } catch {
      setError('Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  // Confirm page
  if (confirming) {
    return (
      <div className="onboarding-root">
        <div className="onboarding-header">
          <h1>Welcome to your Japanese Learning Journey!</h1>
          <p>Review your answers before we get started</p>
          <div className="onboarding-progress-bar">
            <div className="onboarding-progress-fill" style={{ width: '100%' }} />
          </div>
        </div>

        <div className="onboarding-card">
          <h2 className="onboarding-question" style={{ marginBottom: 24 }}>Confirm your answers</h2>

          <div className="confirm-list">
            {QUESTIONS.map((q, i) => (
              <div key={q.id} className="confirm-row">
                <div className="confirm-question">{q.question}</div>
                <div className="confirm-answer-row">
                  <span className="confirm-answer">
                    {getLabel(q.id, answers[q.id as keyof OnboardingAnswers] ?? '')}
                  </span>
                  <button
                    className="confirm-edit"
                    onClick={() => { setConfirming(false); setStep(i) }}
                  >
                    Edit
                  </button>
                </div>
              </div>
            ))}
          </div>

          {error && <p className="onboarding-error">{error}</p>}

          <button
            className="onboarding-submit-btn"
            onClick={submit}
            disabled={submitting}
          >
            {submitting ? 'Saving...' : "Let's Begin →"}
          </button>
        </div>
      </div>
    )
  }

  // Question page
  return (
    <div className="onboarding-root">
      <div className="onboarding-header">
        <h1>Welcome to your Japanese Learning Journey!</h1>
        <p>Answer these questions to get started</p>
        <div className="onboarding-progress-bar">
          <div className="onboarding-progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <span className="onboarding-step-count">{step + 1} / {QUESTIONS.length}</span>
      </div>

      <div className="onboarding-card">
        {q.examples && (
          <div className="onboarding-examples">{q.examples}</div>
        )}
        <h2 className="onboarding-question">{q.question}</h2>

        <div className={`onboarding-options ${q.options.length > 4 ? 'grid' : 'stack'}`}>
          {q.options.map(opt => (
            <button
              key={opt.value}
              className={`onboarding-option ${answers[q.id as keyof OnboardingAnswers] === opt.value ? 'selected' : ''}`}
              onClick={() => select(opt.value)}
            >
              <span className="opt-label">{opt.label}</span>
              <span className="opt-sub">{opt.sub}</span>
            </button>
          ))}
        </div>

        {step > 0 && (
          <button className="onboarding-back" onClick={() => setStep(s => s - 1)}>
            ← Back
          </button>
        )}
      </div>
    </div>
  )
}