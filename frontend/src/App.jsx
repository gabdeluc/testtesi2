import { useState, useEffect, useRef, useCallback } from 'react'
import { Bar, Line, Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js'

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, Tooltip, Legend, Filler
)

const API_URL = 'http://localhost:8000'

// Colore dedicato per ogni partecipante
const PARTICIPANT_COLORS = [
  '#00C7BE',   // Alice  — teal
  '#BF5AF2',   // Bob    — viola
  '#FF9F0A',   // Charlie — arancione
  '#30D158',   // 4° speaker
  '#FF375F',   // 5° speaker
]

const resolveColor = (cfg, participants) => {
  if (!cfg.participantFilter) return cfg.color
  const idx = participants.findIndex(p => p.id === cfg.participantFilter)
  return idx >= 0 ? PARTICIPANT_COLORS[idx] ?? cfg.color : cfg.color
}

const SPEEDS = [1, 2, 5, 10, 20]

const tsToSec = (ts) => {
  if (!ts) return 0
  return new Date(ts).getTime() / 1000
}

let _playbackBase = null

const secToLabel = (sec) => {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ─────────────────────────────────────────────────────────────────────────────
// HOOK PER IL MOBILE RESPONSIVENESS
// ─────────────────────────────────────────────────────────────────────────────
function useMediaQuery(query) {
  const [matches, setMatches] = useState(false)
  useEffect(() => {
    const media = window.matchMedia(query)
    if (media.matches !== matches) setMatches(media.matches)
    const listener = () => setMatches(media.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [matches, query])
  return matches
}

// ─────────────────────────────────────────────────────────────────────────────
// APP
// ─────────────────────────────────────────────────────────────────────────────
function App() {
  // ── Mobile Breakpoint ─────────────────────────────────────────────
  const isMobile = useMediaQuery('(max-width: 768px)')

  // ── Data ─────────────────────────────────────────────────────────
  const [allTranscript, setAllTranscript] = useState([])
  const [participants, setParticipants]   = useState([])
  const [loading, setLoading]             = useState(false)
  const [error, setError]                 = useState(null)

  // ── Playback ──────────────────────────────────────────────────────
  const [playbackIndex, setPlaybackIndex] = useState(0)
  const [isPlaying, setIsPlaying]         = useState(false)
  const [speed, setSpeed]                 = useState(5)
  const timerRef  = useRef(null)
  const indexRef  = useRef(0)

  const [wallSec, setWallSec]   = useState(0)
  const wallRef   = useRef(0)
  const clockRef  = useRef(null)

  // ── UI ────────────────────────────────────────────────────────────
  const [widgetConfigs, setWidgetConfigs] = useState({
    messages:          { participantFilter: null, color: '#FF3B30' },
    sentiment:         { participantFilter: null, color: '#34C759' },
    toxicity:          { participantFilter: null, color: '#FF9500' },
    sentimentDist:     { participantFilter: null, color: '#007AFF', _defaultColor: '#007AFF', showLabels: true },
    toxicityGauge:     { participantFilter: null, color: '#5856D6' },
    timelineSentiment: { participantFilter: null, color: '#00C7BE', showGrid: true, showArea: true, metric: 'sentiment' },
    timelineToxicity:  { participantFilter: null, color: '#FF6B6B', showGrid: true, showArea: true, metric: 'toxicity' },
    messageStream:     { participantFilter: null, color: '#FF2D55', limit: 30, showTimestamps: true },
    participantRoster: { participantFilter: null, color: '#BF5AF2' }
  })

  const [visibleWidgets, setVisibleWidgets] = useState(() => {
    try {
      const saved = localStorage.getItem('visibleWidgets')
      if (saved) return JSON.parse(saved)
    } catch {}
    
    return {
      messages: true, sentiment: true, toxicity: true, sentimentDist: true,
      toxicityGauge: true, timelineSentiment: true, timelineToxicity: true,
      messageStream: true, participantRoster: true
    }
  })
  
  const [meetingList, setMeetingList]         = useState([])
  const [selectedMeeting, setSelectedMeeting] = useState('mtg001')

  const [openSettings, setOpenSettings]       = useState(null)
  const [showWidgetPanel, setShowWidgetPanel] = useState(false)
  const [sidebarOpen, setSidebarOpen]         = useState(false)
  const [activeView, setActiveView]           = useState('overview')

  // ── Load lista meeting ─────────────────────
  useEffect(() => {
    fetch(`${API_URL}/meetings`)
      .then(r => r.json())
      .then(d => setMeetingList(d.meetings || []))
      .catch(() => {})
  }, [])

  // ── Load data ─────────────────────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setError(null)
      if (typeof stopTimer === 'function') { stopTimer(); stopClock() }
      indexRef.current = 0; wallRef.current = 0
      setPlaybackIndex(0); setWallSec(0); setIsPlaying(false)
      try {
        const [rP, rM] = await Promise.all([
          fetch(`${API_URL}/participants`),
          fetch(`${API_URL}/meeting/${selectedMeeting}/analysis`)
        ])
        if (!rM.ok) throw new Error(`HTTP ${rM.status}`)
        const [dP, dM] = await Promise.all([rP.json(), rM.json()])
        setParticipants(dP.participants)
        setAllTranscript(dM.transcript)
      } catch {
        setError('Unable to load meeting data')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [selectedMeeting]) // eslint-disable-line

  useEffect(() => {
    try { localStorage.setItem('visibleWidgets', JSON.stringify(visibleWidgets)) } catch {}
  }, [visibleWidgets])

  // ── Playback engine ───────────────────────────────────────────────
  const stopTimer = useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
  }, [])

  const stopClock = useCallback(() => {
    if (clockRef.current) { clearInterval(clockRef.current); clockRef.current = null }
  }, [])

  const scheduleNext = useCallback((idx, transcript, spd) => {
    if (idx >= transcript.length) { setIsPlaying(false); return }
    const gap = transcript[idx + 1]
      ? tsToSec(transcript[idx + 1].created_at) - tsToSec(transcript[idx].created_at)
      : 1
    const delay = Math.max(80, (gap * 1000) / spd)
    timerRef.current = setTimeout(() => {
      const next = idx + 1
      indexRef.current = next
      setPlaybackIndex(next)
      if (transcript[next - 1]) {
        wallRef.current = tsToSec(transcript[next - 1].created_at) - tsToSec(transcript[0].created_at)
      }
      scheduleNext(next, transcript, spd)
    }, delay)
  }, [])

  const startClock = useCallback((spd) => {
    stopClock()
    clockRef.current = setInterval(() => {
      wallRef.current += 0.1 * spd
      setWallSec(wallRef.current)
    }, 100)
  }, [stopClock])

  useEffect(() => {
    if (isPlaying && allTranscript.length > 0) {
      if (indexRef.current >= allTranscript.length) {
        indexRef.current = 0
        wallRef.current  = 0
        setPlaybackIndex(0)
        setWallSec(0)
      }
      scheduleNext(indexRef.current, allTranscript, speed)
      startClock(speed)
    } else {
      stopTimer()
      stopClock()
    }
    return () => { stopTimer(); stopClock() }
  }, [isPlaying, allTranscript, speed, scheduleNext, startClock, stopTimer, stopClock])

  const handlePlayPause = () => setIsPlaying(p => !p)

  const handleReset = () => {
    stopTimer()
    stopClock()
    setIsPlaying(false)
    indexRef.current = 0
    wallRef.current  = 0
    setPlaybackIndex(0)
    setWallSec(0)
  }

  const handleSpeedChange = (s) => {
    setSpeed(s)
    if (isPlaying) {
      stopTimer()
      stopClock()
      setIsPlaying(false)
      setTimeout(() => setIsPlaying(true), 30)
    }
  }

  const liveTranscript = allTranscript.slice(0, playbackIndex)
  const total          = allTranscript.length
  const baseTs   = total > 0 ? tsToSec(allTranscript[0].created_at) : 0
  const totalSec = total > 0 ? tsToSec(allTranscript[total - 1].created_at) - baseTs : 0
  const progressPct    = totalSec > 0 ? Math.min((wallSec / totalSec) * 100, 100) : 0
  const isFinished     = playbackIndex >= total && total > 0
  const currentTs      = secToLabel(Math.min(wallSec, totalSec))
  const totalTs        = secToLabel(totalSec)

  const updateWidgetConfig   = (id, u) => setWidgetConfigs(p => ({ ...p, [id]: { ...p[id], ...u } }))
  const toggleWidget         = (id)    => setVisibleWidgets(p => ({ ...p, [id]: !p[id] }))

  const getFiltered = (widgetId) => {
    const pf = widgetConfigs[widgetId].participantFilter
    if (!pf) return liveTranscript
    const p = participants.find(x => x.id === pf)
    return p ? liveTranscript.filter(e => e.participant_name === p.name) : liveTranscript
  }

  const calcStats = (tr) => {
    if (!tr?.length) return {
      total_messages: 0,
      sentiment: { distribution: { positive: 0, neutral: 0, negative: 0 }, average_score: 0, positive_ratio: 0, average_polarity: 0 },
      toxicity:  { toxic_count: 0, toxic_ratio: 0, severity_distribution: { low: 0, medium: 0, high: 0 }, average_toxicity_score: 0 }
    }
    const SIGN = { positive: 1, neutral: 0, negative: -1 }
    let sc = 0, pol = 0, tx = 0
    const d = { positive: 0, neutral: 0, negative: 0 }
    const sv = { low: 0, medium: 0, high: 0 }
    let tc = 0
    tr.forEach(e => {
      const { label, score, confidence } = e.sentiment
      if (d[label] !== undefined) d[label]++
      sc  += score
      pol += (SIGN[label] ?? 0) * score * confidence
      if (e.toxicity.is_toxic) tc++
      if (sv[e.toxicity.severity] !== undefined) sv[e.toxicity.severity]++
      tx  += e.toxicity.toxicity_score
    })
    const n = tr.length
    return {
      total_messages: n,
      sentiment: { distribution: d, average_score: sc/n, positive_ratio: d.positive/n, average_polarity: pol/n },
      toxicity:  { toxic_count: tc, toxic_ratio: tc/n, severity_distribution: sv, average_toxicity_score: tx/n }
    }
  }

  const getParticipantStats = () =>
    participants.map(p => {
      const msgs = liveTranscript.filter(e => e.participant_name === p.name)
      return { ...p, stats: calcStats(msgs) }
    })

  const sections = [
    { title: 'Participants', items: [
      { id: 'participantRoster', name: 'Participant Roster', desc: 'Per-participant sentiment breakdown and weighted polarity [−1,+1]. Updates live as the meeting progresses.' }
    ]},
    { title: 'Key Metrics', items: [
      { id: 'messages',  name: 'Messages',          desc: 'Running count of messages seen so far during the playback.' },
      { id: 'sentiment', name: 'Sentiment Overview', desc: 'Weighted polarity on a bipolar scale [−1,+1], updated in real time as new messages arrive.' },
      { id: 'toxicity',  name: 'Toxic Messages',    desc: 'Count and % of toxic messages detected so far. Toggle off if the dataset has no aggressive language.' }
    ]},
    { title: 'Analytics', items: [
      { id: 'sentimentDist',     name: 'Sentiment Distribution', desc: 'Stacked bar of positive/neutral/negative proportion accumulated so far.' },
      { id: 'timelineSentiment', name: 'Sentiment Timeline',     desc: 'Line chart of sentiment score — each point is one message. Grows as the meeting plays.' },
      { id: 'timelineToxicity',  name: 'Toxicity Timeline',      desc: 'Line chart of toxicity score — highlights aggressive spikes in real time.' },
      { id: 'toxicityGauge',     name: 'Toxicity Severity',      desc: 'Doughnut gauge of current average toxicity. Distinguishes low/medium/high without digging into numbers.' }
    ]},
    { title: 'Content', items: [
      { id: 'messageStream', name: 'Message Stream', desc: 'Live feed of incoming messages with colour-coded sentiment and toxicity badges. New messages appear at the top.' }
    ]}
  ]

  return (
    <div style={S.app}>
      {/* Layout Flex: Colonna su mobile, riga su desktop */}
      <div style={{ display:'flex', flexDirection: isMobile ? 'column' : 'row', minHeight:'100vh' }}>

      {/* ══ SIDEBAR / BOTTOM NAV ═════════════════════════════════════════ */}
      <nav style={{
        ...S.sidebar,
        width: isMobile ? '100%' : (sidebarOpen ? 200 : 56),
        height: isMobile ? 'auto' : '100vh',
        position: isMobile ? 'fixed' : 'sticky',
        bottom: isMobile ? 0 : 'auto',
        flexDirection: isMobile ? 'row' : 'column',
        justifyContent: isMobile ? 'space-around' : 'flex-start',
        padding: isMobile ? '8px 4px' : '10px 0',
        zIndex: 100,
        borderTop: isMobile ? '0.5px solid rgba(255,255,255,0.08)' : 'none',
        borderRight: isMobile ? 'none' : '0.5px solid rgba(255,255,255,0.08)'
      }}>
        {!isMobile && (
          <button
            onClick={() => setSidebarOpen(o => !o)}
            style={S.sbToggle}
            title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {sidebarOpen ? '←' : '☰'}
          </button>
        )}

        {!isMobile && <div style={S.sbDivider} />}

        {NAV_ITEMS.map(item => {
          const isActive = activeView === item.id
          return (
            <button
              key={item.id}
              onClick={() => setActiveView(item.id)}
              style={{
                ...S.sbItem,
                backgroundColor: isActive ? 'rgba(0,122,255,0.15)' : 'transparent',
                borderLeft: (!isMobile && isActive) ? '2px solid #007AFF' : (!isMobile ? '2px solid transparent' : 'none'),
                borderBottom: (isMobile && isActive) ? '2px solid #007AFF' : (isMobile ? '2px solid transparent' : 'none'),
                color: isActive ? '#fff' : '#8e8e93',
                flexDirection: isMobile ? 'column' : 'row',
                padding: isMobile ? '6px 4px' : '10px 14px',
                justifyContent: isMobile ? 'center' : 'flex-start',
                gap: isMobile ? 4 : 10,
                flex: isMobile ? 1 : 'none'
              }}
              title={(!sidebarOpen && !isMobile) ? item.label : undefined}
            >
              <span style={{ ...S.sbIcon, color: isActive ? '#007AFF' : '#636366' }}>{item.icon}</span>
              {(sidebarOpen || isMobile) && (
                <span style={{ ...S.sbLabel, fontSize: isMobile ? 10 : 13, color: isActive ? '#fff' : '#8e8e93' }}>
                  {item.label}
                </span>
              )}
            </button>
          )
        })}

        {!isMobile && <div style={{ flex:1 }} />}
        {!isMobile && sidebarOpen && (
          <div style={S.sbFooter}>Meeting<br/>Intelligence</div>
        )}
      </nav>

      {/* ══ MAIN CONTENT ═══════════════════════════════════════════ */}
      {/* PaddingBottom extra su mobile per non nascondere contenuti sotto la bottom nav */}
      <div style={{ flex:1, minWidth:0, paddingBottom: isMobile ? 80 : 0 }}>

      {/* ══ HEADER ══════════════════════════════════════════════════ */}
      <div style={S.header}>
        <div style={{ ...S.hRow, padding: isMobile ? '12px 16px 8px' : '12px 20px 8px' }}>
          
          <div style={S.hLeft}>
            {!isMobile && <div style={S.logo}>MI</div>}
            <div>
              <h1 style={{ ...S.title, fontSize: isMobile ? 15 : 17 }}>Meeting Intelligence</h1>
              {!isMobile && <p style={S.subtitle}>{selectedMeeting.toUpperCase()} · Live Playback</p>}
            </div>
          </div>

          <div style={S.hRight}>
            {meetingList.length > 0 && (
              <select
                value={selectedMeeting}
                onChange={e => setSelectedMeeting(e.target.value)}
                style={{ ...S.meetingSelect, display: isMobile ? 'none' : 'block' }}
              >
                {meetingList.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.id.toUpperCase()} · {new Date(m.date).toLocaleDateString('it-IT', { day:'2-digit', month:'short' })}
                  </option>
                ))}
              </select>
            )}

            <button onClick={handleReset} style={S.ctrlBtn} title="Restart">⏮</button>
            <button
              onClick={handlePlayPause}
              style={{ ...S.ctrlBtn, backgroundColor: isPlaying ? '#FF9500' : '#34C759', minWidth: isMobile ? 40 : 76 }}
            >
              {isPlaying ? '⏸' : isFinished ? '↺' : '▶'} {!isMobile && (isPlaying ? 'Pause' : isFinished ? 'Replay' : 'Play')}
            </button>

            <div style={S.speedGroup}>
              {SPEEDS.map(s => (
                <button key={s} onClick={() => handleSpeedChange(s)}
                  style={{ ...S.speedBtn, ...(speed === s ? S.speedActive : {}) }}>
                  {s}×
                </button>
              ))}
            </div>

            {!isMobile && (
              <div style={S.tsBlock}>
                <span style={S.tsCurr}>{currentTs}</span>
                <span style={{ color: '#636366', fontSize: 12 }}> / </span>
                <span style={S.tsTotal}>{totalTs}</span>
              </div>
            )}

            <button onClick={() => setShowWidgetPanel(v => !v)} style={{...S.custBtn, padding: isMobile ? '6px 10px' : '7px 14px'}}>
              ⚙️ {!isMobile && <span style={{ marginLeft: 4 }}>Customize</span>}
            </button>
          </div>
        </div>

        <div style={S.barOuter}>
          <div style={{
            ...S.barInner,
            width: `${progressPct}%`,
            backgroundColor: isFinished ? '#34C759' : isPlaying ? '#007AFF' : '#636366'
          }} />
        </div>
        <div style={S.barStats}>
          <span>{playbackIndex} / {total} messages</span>
          <span style={{ color: isPlaying ? '#007AFF' : isFinished ? '#34C759' : '#636366' }}>
            {isPlaying ? `● Live  ${speed}×` : isFinished ? '✓ Completed' : '⏸ Paused'}
          </span>
        </div>
      </div>

      {/* ══ CUSTOMIZE PANEL ════════════════════════════════════════ */}
      {showWidgetPanel && (
        <div style={S.overlayBg} onClick={() => setShowWidgetPanel(false)}>
          <div style={S.sidePanel} onClick={e => e.stopPropagation()}>
            <div style={S.spHead}>
              <span style={S.spTitle}>Customize Dashboard</span>
              <button onClick={() => setShowWidgetPanel(false)} style={S.spClose}>Close</button>
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {sections.map(sec => (
                <div key={sec.title}>
                  <div style={S.secLabel}>{sec.title}</div>
                  {sec.items.map((w, wi) => (
                    <div key={w.id}>
                      <div style={S.wRow} onClick={() => toggleWidget(w.id)}>
                        <div style={{ flex: 1 }}>
                          <div style={S.wName}>{w.name}</div>
                          <div style={S.wDesc}>{w.desc}</div>
                        </div>
                        <button
                          style={{ ...S.togBtn, backgroundColor: visibleWidgets[w.id] ? '#007AFF' : '#3a3a3c', color: visibleWidgets[w.id] ? '#fff' : '#8e8e93' }}
                          onClick={e => { e.stopPropagation(); toggleWidget(w.id) }}
                        >
                          {visibleWidgets[w.id] ? 'ON' : 'OFF'}
                        </button>
                      </div>
                      {wi < sec.items.length - 1 && <div style={S.div} />}
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div style={S.spFoot}>
              {Object.values(visibleWidgets).filter(Boolean).length} / {Object.keys(visibleWidgets).length} widgets enabled
            </div>
          </div>
        </div>
      )}

      {/* ══ ERROR ══════════════════════════════════════════════════ */}
      {error && <div style={S.errBanner}>⚠ {error}</div>}

      {/* ══ LOADING ════════════════════════════════════════════════ */}
      {loading && (
        <div style={S.loadBox}>
          <div style={S.spinner} />
          <p style={{ color: '#8e8e93', marginTop: 12 }}>Loading meeting data…</p>
        </div>
      )}

      {/* ══ EMPTY STATE ════════════════════════════════════════════ */}
      {!loading && !error && total > 0 && playbackIndex === 0 && !isPlaying && (
        <div style={S.emptyBox}>
          <div style={{ fontSize: 52, color: '#3a3a3c' }}>▶</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', marginTop: 8 }}>Ready to play</div>
          <div style={{ fontSize: 14, color: '#8e8e93', textAlign: 'center', lineHeight: 1.6, maxWidth: 360 }}>
            {total} messages · {totalTs} meeting duration<br />
            Press <strong style={{ color: '#fff' }}>Play</strong> to watch the meeting unfold in real time.
            Use the speed selector to go faster.
          </div>
          <button onClick={handlePlayPause} style={S.bigPlay}>▶ Start Playback</button>
        </div>
      )}

      {/* ══ WIDGET GRID ════════════════════════════════════════════ */}
      {!loading && liveTranscript.length > 0 && (() => {

        const wgt = (id, title, wide, children) => (
          <Wgt key={id} id={id} title={title} wide={!isMobile && wide} // Wide viene disabilitato su mobile per flow naturale
            cfg={widgetConfigs[id]} participants={participants}
            onCfg={u => updateWidgetConfig(id, u)}
            open={openSettings} setOpen={setOpenSettings}>
            {children}
          </Wgt>
        )
        const col = (id) => resolveColor(widgetConfigs[id], participants)

        const kpiMessages = wgt('messages', 'Messages', false,
          (() => { const d = getFiltered('messages')
            return <><div style={S.kpiVal}>{d.length}</div><div style={S.kpiLab}>messages so far</div></> })())
        const kpiSentiment = wgt('sentiment', 'Sentiment', false,
          (() => { const s = calcStats(getFiltered('sentiment'))
            return <PolarityKPI polarity={s.sentiment.average_polarity} posRatio={s.sentiment.positive_ratio} accentColor={col('sentiment')} /> })())
        const kpiToxicity = wgt('toxicity', 'Toxic Messages', false,
          (() => { const s = calcStats(getFiltered('toxicity'))
            return <><div style={{ ...S.kpiVal, color: col('toxicity') }}>{s.toxicity.toxic_count}</div><div style={S.kpiLab}>{(s.toxicity.toxic_ratio*100).toFixed(0)}% toxic</div></> })())
        const wSentDist = wgt('sentimentDist', 'Sentiment Distribution', true,
          (() => { const s = calcStats(getFiltered('sentimentDist'))
            return <SentimentDistChart data={s.sentiment.distribution} cfg={{ ...widgetConfigs.sentimentDist, color: col('sentimentDist') }} /> })())
        const wTimeSent = wgt('timelineSentiment', 'Sentiment Timeline', true,
          <TimelineChart messages={getFiltered('timelineSentiment')} cfg={{ ...widgetConfigs.timelineSentiment, color: col('timelineSentiment') }} />)
        const wTimeTox = wgt('timelineToxicity', 'Toxicity Timeline', true,
          <TimelineChart messages={getFiltered('timelineToxicity')} cfg={{ ...widgetConfigs.timelineToxicity, color: col('timelineToxicity') }} />)
        const wGauge = wgt('toxicityGauge', 'Toxicity Severity', false,
          (() => { const s = calcStats(getFiltered('toxicityGauge'))
            return <ToxicityGauge score={s.toxicity.average_toxicity_score} accentColor={col('toxicityGauge')} /> })())
        const wRoster = wgt('participantRoster', 'Participant Roster', true,
          <ParticipantRoster stats={getParticipantStats()} participantColors={PARTICIPANT_COLORS} isMobile={isMobile} />)
        const wStream = wgt('messageStream', 'Message Stream', true,
          <MessageStream messages={getFiltered('messageStream')} cfg={widgetConfigs.messageStream} participantColors={PARTICIPANT_COLORS} participants={participants} />)

        const allViews = {
          overview:     [wRoster, kpiMessages, kpiSentiment, kpiToxicity,
                         wSentDist, wTimeSent, wTimeTox, wGauge, wStream],
          sentiment:    [kpiSentiment, wSentDist, wTimeSent],
          toxicity:     [kpiToxicity, wTimeTox, wGauge],
          participants: [wRoster],
          stream:       [kpiMessages, wStream],
        }

        const activeWidgets = (allViews[activeView] || allViews.overview)
          .filter(w => {
            const wid = w?.props?.id
            return wid ? visibleWidgets[wid] !== false : true
          })

        return (
          <div style={{
            ...S.grid,
            // Cambio dinamico della griglia su mobile: 1 colonna fissa
            gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill,minmax(280px,1fr))'
          }}>
            {activeView !== 'overview' && (
              <div style={S.viewTitle}>
                {NAV_ITEMS.find(n => n.id === activeView)?.icon}{' '}
                {NAV_ITEMS.find(n => n.id === activeView)?.label}
              </div>
            )}
            {activeWidgets}
          </div>
        )
      })()}
      </div>
      </div>
    </div>
  )
}

const NAV_ITEMS = [
  { id: 'overview',     icon: '⊞', label: 'Overview'    },
  { id: 'sentiment',    icon: '◎', label: 'Sentiment'   },
  { id: 'toxicity',     icon: '⚠', label: 'Toxicity'    },
  { id: 'participants', icon: '👥', label: 'Participants' },
  { id: 'stream',       icon: '▤', label: 'Stream'      },
]

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENTI E WIDGETS
// ─────────────────────────────────────────────────────────────────────────────

function Wgt({ id, title, children, wide, cfg, participants, onCfg, open, setOpen }) {
  const isOpen = open === id
  return (
    <div style={{ ...S.widget, ...(wide ? S.widgetWide : {}) }}>
      <div style={S.wHead}>
        <span style={S.wTitle}>{title}</span>
        <button onClick={() => setOpen(isOpen ? null : id)} style={S.wBtn}>{isOpen ? '✕' : '⋯'}</button>
      </div>
      {isOpen && (
        <div style={S.setPanel}>
          <span style={S.setLabel}>Participant</span>
          <select value={cfg.participantFilter || ''} onChange={e => onCfg({ participantFilter: e.target.value || null })} style={S.setSelect}>
            <option value="">All</option>
            {participants.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
      <div style={S.wBody}>{children}</div>
    </div>
  )
}

function PolarityKPI({ polarity, posRatio, accentColor }) {
  const p     = polarity ?? 0
  const semanticColor = p >  0.05 ? '#34C759' : p < -0.05 ? '#FF3B30' : '#FFCC00'
  const color = accentColor || semanticColor
  const label = p >  0.5  ? 'Very Positive' : p >  0.1 ? 'Positive'
              : p < -0.5  ? 'Very Negative' : p < -0.1 ? 'Negative' : 'Neutral'
  const cur   = ((p + 1) / 2) * 100
  return (
    <div style={{ padding: '4px 0' }}>
      <div style={{ fontSize: 36, fontWeight: 700, color, lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
        {p >= 0 ? '+' : ''}{p.toFixed(3)}
      </div>
      <div style={{ fontSize: 12, color, fontWeight: 600, marginTop: 2 }}>{label}</div>
      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#636366', marginBottom: 4 }}>
          <span>−1</span><span style={{ color: '#8e8e93' }}>Polarity scale</span><span>+1</span>
        </div>
        <div style={{ position: 'relative', height: 6, borderRadius: 3, background: 'linear-gradient(to right,#FF3B30,#FFCC00 50%,#34C759)' }}>
          <div style={{ position: 'absolute', left: '50%', top: -2, width: 1, height: 10, backgroundColor: 'rgba(255,255,255,0.25)' }} />
          <div style={{ position: 'absolute', left: `${cur}%`, top: '50%', transform: 'translate(-50%,-50%)', width: 12, height: 12, borderRadius: '50%', backgroundColor: color, border: '2px solid #1c1c1e', boxShadow: `0 0 6px ${color}`, transition: 'left 0.4s ease' }} />
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#636366', marginTop: 8 }}>
        {(posRatio * 100).toFixed(0)}% positive · weighted by confidence
      </div>
    </div>
  )
}

const AV_COLORS = ['#5856D6','#007AFF','#34C759','#FF9500','#FF2D55','#BF5AF2']

function ParticipantRoster({ stats, participantColors, isMobile }) {
  if (!stats?.length) return <div style={S.empty}>No data yet — press Play</div>
  return (
    <div style={{ 
      display: 'grid', 
      // Anche il roster dei partecipanti collassa su una singola colonna su mobile
      gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill,minmax(210px,1fr))', 
      gap: 14 
    }}>
      {stats.map((p, i) => {
        const pColor = (participantColors && participantColors[i]) || AV_COLORS[i % AV_COLORS.length]
        const n   = p.stats.total_messages
        const d   = p.stats.sentiment.distribution
        const pol = p.stats.sentiment.average_polarity ?? 0
        const pc  = pol >= 0 ? '#34C759' : '#FF3B30'
        const tr  = n ? (p.stats.toxicity.toxic_count / n * 100).toFixed(0) : 0
        const dom = d.positive >= d.neutral && d.positive >= d.negative ? 'positive'
          : d.negative > d.positive && d.negative >= d.neutral ? 'negative' : 'neutral'
        const dc  = { positive: '#34C759', neutral: '#FFCC00', negative: '#FF3B30' }[dom]
        return (
          <div key={p.id} style={{ ...R.card, borderColor: pColor + '44' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ ...R.av, backgroundColor: pColor }}>
                {p.name.slice(0,2).toUpperCase()}
              </div>
              <div>
                <div style={R.name}>{p.name}</div>
                <span style={{ ...R.badge, backgroundColor: dc+'22', color: dc }}>{dom}</span>
              </div>
            </div>
            <div style={{ fontSize: 10, color: '#8e8e93', marginTop: 6 }}>Sentiment breakdown</div>
            <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', backgroundColor: 'rgba(255,255,255,0.07)' }}>
              {n > 0 && <>
  <div style={{ width: `${d.positive/n*100}%`, backgroundColor: '#34C759', transition: 'width 0.4s' }} />
  <div style={{ width: `${d.neutral/n*100}%`,  backgroundColor: '#FFCC00', transition: 'width 0.4s' }} />
  <div style={{ width: `${d.negative/n*100}%`, backgroundColor: '#FF3B30', transition: 'width 0.4s' }} />
</>}
            </div>
            <div style={{ display: 'flex', gap: 8, fontSize: 10, color: '#8e8e93', marginTop: 3 }}>
              <span><span style={{ color: '#34C759' }}>●</span> {d.positive}</span>
              <span><span style={{ color: '#FFCC00' }}>●</span> {d.neutral}</span>
              <span><span style={{ color: '#FF3B30' }}>●</span> {d.negative}</span>
            </div>
            <div style={R.kRow}>
              <div style={R.kCell}><div style={R.kV}>{n}</div><div style={R.kL}>msg</div></div>
              <div style={R.kCell}><div style={{ ...R.kV, color: pc }}>{pol >= 0 ? '+' : ''}{pol.toFixed(2)}</div><div style={R.kL}>polarity</div></div>
              <div style={R.kCell}><div style={{ ...R.kV, color: p.stats.toxicity.toxic_count > 0 ? '#FF3B30' : '#34C759' }}>{tr}%</div><div style={R.kL}>toxic</div></div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const R = {
  card:  { backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 14, padding: 14, border: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column', gap: 7 },
  av:    { width: 38, height: 38, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13, color: '#fff', flexShrink: 0 },
  name:  { fontSize: 14, fontWeight: 600, color: '#fff' },
  badge: { fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', padding: '2px 6px', borderRadius: 5, display: 'inline-block', marginTop: 2 },
  kRow:  { display: 'flex', justifyContent: 'space-between', backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 8, padding: '8px 4px', marginTop: 4 },
  kCell: { display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 },
  kV:    { fontSize: 15, fontWeight: 700, color: '#fff' },
  kL:    { fontSize: 9, color: '#636366', textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: 1 }
}

function SentimentDistChart({ data, cfg }) {
  const tot = (data.positive||0)+(data.neutral||0)+(data.negative||0)
  if (tot === 0) return <div style={S.empty}>No data yet</div>
  const hasParticipant = cfg.color !== cfg._defaultColor
  const posCol = '#34C759', neuCol = '#FFCC00', negCol = '#FF3B30'
  const acCol  = cfg.color || posCol
  const [c1, c2, c3] = hasParticipant ? [acCol, acCol + 'AA', acCol + '66'] : [posCol, neuCol, negCol]
  return (
    <div style={{ height: 140 }}>
      <Bar
        data={{ labels:['Distribution'], datasets:[
          { label:'Positive', data:[data.positive], backgroundColor:c1, borderRadius:6 },
          { label:'Neutral',  data:[data.neutral],  backgroundColor:c2, borderRadius:6 },
          { label:'Negative', data:[data.negative], backgroundColor:c3, borderRadius:6 }
        ]}}
        options={{ indexAxis:'y', responsive:true, maintainAspectRatio:false, animation:{ duration:250 },
          plugins:{ legend:{ display:cfg.showLabels, position:'bottom', labels:{ color:'#8e8e93', font:{ size:11 } } },
            tooltip:{ backgroundColor:'rgba(28,28,30,0.95)', callbacks:{ label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.x} (${((ctx.parsed.x/tot)*100).toFixed(0)}%)` } } },
          scales:{ x:{ stacked:true, grid:{ color:'rgba(255,255,255,0.05)' }, ticks:{ color:'#8e8e93' } }, y:{ stacked:true, display:false } } }}
      />
    </div>
  )
}

function TimelineChart({ messages, cfg }) {
  if (!messages?.length) return <div style={S.empty}>No data yet</div>
  const base = new Date(messages[0].created_at).getTime()
  const fmt = ts => {
    const diffSec = Math.max(0, (new Date(ts).getTime() - base) / 1000)
    const mm = Math.floor(diffSec / 60), ss = Math.floor(diffSec % 60)
    return `${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}`
  }
  const pts = messages.map(m => ({
    y: cfg.metric==='sentiment' ? m.sentiment.score : m.toxicity.toxicity_score,
    lbl: fmt(m.created_at), nick: m.participant_name, text: m.transcribed_text
  }))
  const step = Math.max(1, Math.floor(messages.length/10))
  const xLbls = pts.map((p,i) => (i===0||i===pts.length-1||i%step===0) ? p.lbl : '')
  const col = cfg.color||'#00C7BE'
  return (
    <div style={{ height: 260 }}>
      <Line
        data={{ labels:xLbls, datasets:[{ label:cfg.metric, data:pts.map(p=>p.y), borderColor:col,
          backgroundColor:cfg.showArea ? col+'22':'transparent', borderWidth:2,
          pointRadius:2, pointHoverRadius:5, fill:cfg.showArea, tension:0.4 }]}}
        options={{ responsive:true, maintainAspectRatio:false, animation:{ duration:150 },
          plugins:{ legend:{ display:false },
            tooltip:{ backgroundColor:'rgba(28,28,30,0.95)', callbacks:{
              title: items=>`${pts[items[0].dataIndex].lbl} · ${pts[items[0].dataIndex].nick}`,
              label: ctx=>`Score: ${ctx.parsed.y.toFixed(3)}`,
              afterLabel: ctx=>{ const t=pts[ctx.dataIndex].transcribed_text; return t.length>50?t.slice(0,50)+'…':t }
            }}},
          scales:{
            x:{ grid:{ color:'rgba(255,255,255,0.05)' }, ticks:{ color:'#8e8e93', maxRotation:0 } },
            y:{ min:0, max:1, grid:{ color:'rgba(255,255,255,0.05)' }, ticks:{ color:'#8e8e93', callback:v=>(v*100).toFixed(0)+'%' } }
          } }}
      />
    </div>
  )
}

function ToxicityGauge({ score, accentColor }) {
  const p = Math.min(Math.max(score||0,0),1)
  const lvl = p<0.33?'Low':p<0.66?'Medium':'High'
  const semanticCol = p<0.33?'#34C759':p<0.66?'#FF9500':'#FF3B30'
  const col = accentColor || semanticCol
  return (
    <div style={{ height:140, position:'relative', display:'flex', alignItems:'center', justifyContent:'center' }}>
      <Doughnut
        data={{ datasets:[{ data:[p,1-p], backgroundColor:[col,'rgba(255,255,255,0.07)'], borderWidth:0, circumference:180, rotation:270 }]}}
        options={{ responsive:true, maintainAspectRatio:false, cutout:'75%', animation:{ duration:300 }, plugins:{ legend:{ display:false }, tooltip:{ enabled:false } } }}
      />
      <div style={{ position:'absolute', bottom:8, textAlign:'center' }}>
        <div style={{ fontSize:20, fontWeight:700, color:col }}>{(p*100).toFixed(0)}%</div>
        <div style={{ fontSize:11, color:'#8e8e93' }}>{lvl} toxicity</div>
      </div>
    </div>
  )
}

function MessageStream({ messages, cfg, participantColors, participants }) {
  if (!messages?.length) return <div style={S.empty}>No messages yet</div>
  const sc = l => ({ positive:'#34C759', neutral:'#FFCC00', negative:'#FF3B30' }[l]||'#8e8e93')
  const base = messages.length ? new Date(messages[0].created_at).getTime() : 0
  const fmt = ts => {
    const diffSec = Math.max(0, (new Date(ts).getTime() - base) / 1000)
    const mm = Math.floor(diffSec / 60), ss = Math.floor(diffSec % 60)
    return `${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}`
  }
  const nickColor = (name) => {
    if (!participantColors || !participants) return '#fff'
    const idx = participants.findIndex(p => p.name === name)
    return idx >= 0 ? (participantColors[idx] || '#fff') : '#fff'
  }
  return (
    <div style={{ maxHeight:380, overflowY:'auto' }}>
      {[...messages].reverse().slice(0, cfg.limit||30).map((m,i) => (
        <div key={i} style={{ padding:'9px 0', borderBottom:'0.5px solid rgba(255,255,255,0.06)' }}>
          <div style={{ display:'flex', gap:7, alignItems:'center', flexWrap:'wrap', marginBottom:3 }}>
            <span style={{ fontSize:12, fontWeight:600, color: nickColor(m.participant_name) }}>{m.participant_name}</span>
            {cfg.showTimestamps && <span style={{ fontSize:11, color:'#636366' }}>{fmt(m.created_at)}</span>}
            <span style={{ fontSize:10, fontWeight:600, padding:'2px 6px', borderRadius:5, backgroundColor:sc(m.sentiment.label)+'22', color:sc(m.sentiment.label), textTransform:'uppercase' }}>
              {m.sentiment.label}
            </span>
            {m.toxicity.is_toxic && (
              <span style={{ fontSize:10, fontWeight:600, padding:'2px 6px', borderRadius:5, backgroundColor:'#FF3B3022', color:'#FF3B30' }}>
                ⚠ {m.toxicity.severity}
              </span>
            )}
          </div>
          <div style={{ fontSize:13, color:'#ebebf5cc', lineHeight:1.5 }}>{m.transcribed_text}</div>
        </div>
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// STYLES
// ─────────────────────────────────────────────────────────────────────────────
const S = {
  app:    { backgroundColor:'#1c1c1e', fontFamily:'-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif', color:'#fff' },

  sidebar:  { backgroundColor:'rgba(20,20,22,0.98)', display:'flex', alignItems:'stretch', transition:'width 0.25s ease', overflow:'hidden' },
  sbToggle: { background:'none', border:'none', color:'#8e8e93', cursor:'pointer', fontSize:18, padding:'8px 0', width:'100%', display:'flex', alignItems:'center', justifyContent:'center', lineHeight:1, marginBottom:4, transition:'color 0.2s' },
  sbDivider:{ height:'0.5px', backgroundColor:'rgba(255,255,255,0.07)', margin:'4px 10px 8px' },
  sbItem:   { background:'none', border:'none', cursor:'pointer', display:'flex', alignItems:'center', fontWeight:500, textAlign:'left', overflow:'hidden', width:'100%', transition:'background 0.15s' },
  sbIcon:   { fontSize:17, flexShrink:0, width:22, textAlign:'center' },
  sbLabel:  { fontWeight:500, opacity:1, transition:'opacity 0.2s', whiteSpace:'nowrap' },
  sbFooter: { fontSize:10, color:'#3a3a3c', padding:'12px 14px', lineHeight:1.4, fontWeight:600, textTransform:'uppercase', letterSpacing:'0.5px' },

  header: { position:'sticky', top:0, zIndex:95, backgroundColor:'rgba(28,28,30,0.96)', backdropFilter:'saturate(180%) blur(20px)', borderBottom:'0.5px solid rgba(255,255,255,0.1)' },
  hRow:   { maxWidth:1400, margin:'0 auto', display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10 },
  hLeft:  { display:'flex', alignItems:'center', gap:12 },
  hRight: { display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' },
  logo:   { width:36, height:36, borderRadius:'50%', background:'linear-gradient(135deg,#007AFF,#5856D6)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, color:'#fff', flexShrink:0 },
  title:  { fontWeight:700, margin:0 },
  subtitle:{ fontSize:12, color:'#8e8e93', margin:0 },

  meetingSelect: { backgroundColor:'rgba(255,255,255,0.08)', border:'0.5px solid rgba(255,255,255,0.18)', borderRadius:10, color:'#fff', padding:'7px 12px', fontSize:13, fontWeight:600, cursor:'pointer', outline:'none' },

  ctrlBtn:    { border:'none', borderRadius:8, padding:'6px 12px', fontSize:13, color:'#fff', cursor:'pointer', backgroundColor:'#3a3a3c', fontWeight:600 },
  speedGroup: { display:'flex', gap:3, backgroundColor:'rgba(255,255,255,0.07)', borderRadius:8, padding:3 },
  speedBtn:   { border:'none', borderRadius:6, padding:'4px 9px', fontSize:12, color:'#8e8e93', cursor:'pointer', backgroundColor:'transparent', fontWeight:500 },
  speedActive:{ backgroundColor:'#007AFF', color:'#fff', fontWeight:700 },
  tsBlock:    { display:'flex', alignItems:'center', gap:2, fontVariantNumeric:'tabular-nums' },
  tsCurr:     { fontSize:14, fontWeight:700, color:'#fff' },
  tsTotal:    { fontSize:12, color:'#8e8e93' },
  custBtn:    { display:'flex', alignItems:'center', backgroundColor:'rgba(255,255,255,0.08)', border:'0.5px solid rgba(255,255,255,0.18)', borderRadius:10, color:'#fff', cursor:'pointer', fontSize:13, fontWeight:500 },

  barOuter: { height:4, backgroundColor:'rgba(255,255,255,0.07)' },
  barInner: { height:'100%', transition:'width 0.3s ease, background-color 0.5s' },
  barStats: { display:'flex', justifyContent:'space-between', padding:'4px 20px 6px', fontSize:11, color:'#636366' },

  overlayBg: { position:'fixed', inset:0, backgroundColor:'rgba(0,0,0,0.5)', zIndex:200, display:'flex', justifyContent:'flex-end' },
  sidePanel: { width:'clamp(300px,90vw,420px)', height:'100%', backgroundColor:'#1c1c1e', borderLeft:'0.5px solid rgba(255,255,255,0.1)', display:'flex', flexDirection:'column', overflowY:'hidden' },
  spHead:    { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'18px 20px', borderBottom:'0.5px solid rgba(255,255,255,0.08)' },
  spTitle:   { fontSize:16, fontWeight:700, color:'#fff' },
  spClose:   { background:'none', border:'none', color:'#007AFF', cursor:'pointer', fontSize:14 },
  spFoot:    { padding:'10px 20px', borderTop:'0.5px solid rgba(255,255,255,0.08)', fontSize:12, color:'#636366', textAlign:'center' },
  secLabel:  { fontSize:11, fontWeight:600, color:'#636366', textTransform:'uppercase', letterSpacing:'0.8px', padding:'14px 20px 6px' },
  wRow:      { display:'flex', alignItems:'flex-start', justifyContent:'space-between', padding:'13px 20px', cursor:'pointer', gap:10 },
  wName:     { fontSize:14, fontWeight:500, color:'#fff', marginBottom:3 },
  wDesc:     { fontSize:12, color:'#8e8e93', lineHeight:1.45 },
  togBtn:    { border:'none', borderRadius:7, padding:'5px 12px', cursor:'pointer', fontSize:12, fontWeight:600, flexShrink:0, marginTop:2 },
  div:       { height:'0.5px', backgroundColor:'rgba(255,255,255,0.06)', margin:'0 20px' },

  grid:      { maxWidth:1400, margin:'0 auto', padding:'clamp(1rem,3vw,1.5rem)', display:'grid', gap:'clamp(0.75rem,2vw,1rem)', alignItems:'start' },
  widget:    { backgroundColor:'rgba(255,255,255,0.05)', borderRadius:16, border:'0.5px solid rgba(255,255,255,0.1)', overflow:'hidden' },
  widgetWide:{ gridColumn:'1 / -1' },
  wHead:     { display:'flex', justifyContent:'space-between', alignItems:'center', padding:'13px 15px 0' },
  wTitle:    { fontSize:12, fontWeight:600, color:'#8e8e93', textTransform:'uppercase', letterSpacing:'0.5px' },
  wBtn:      { background:'none', border:'none', color:'#636366', cursor:'pointer', fontSize:18, padding:'0 3px', lineHeight:1 },
  setPanel:  { margin:'8px 15px', padding:'10px 12px', backgroundColor:'rgba(0,0,0,0.3)', borderRadius:9, display:'flex', alignItems:'center', gap:10 },
  setLabel:  { fontSize:12, color:'#8e8e93', whiteSpace:'nowrap' },
  setSelect: { flex:1, backgroundColor:'rgba(255,255,255,0.1)', border:'0.5px solid rgba(255,255,255,0.15)', borderRadius:7, color:'#fff', padding:'4px 8px', fontSize:12 },
  wBody:     { padding:'10px 15px 15px' },

  viewTitle: { gridColumn:'1/-1', fontSize:20, fontWeight:700, color:'#fff', padding:'4px 0 8px', display:'flex', alignItems:'center', gap:8 },

  kpiVal:    { fontSize:40, fontWeight:700, color:'#fff', lineHeight:1 },
  kpiLab:    { fontSize:12, color:'#8e8e93', marginTop:4 },

  loadBox:   { display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', height:'60vh' },
  spinner:   { width:32, height:32, border:'3px solid rgba(255,255,255,0.1)', borderTop:'3px solid #007AFF', borderRadius:'50%', animation:'spin 1s linear infinite' },
  errBanner: { backgroundColor:'rgba(255,59,48,0.15)', border:'0.5px solid rgba(255,59,48,0.3)', borderRadius:10, padding:'12px 20px', margin:16, color:'#FF3B30', fontSize:14 },
  empty:     { color:'#636366', fontSize:13, textAlign:'center', padding:'18px 0' },
  emptyBox:  { display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', minHeight:'65vh', gap:16, padding:24 },
  bigPlay:   { backgroundColor:'#34C759', border:'none', borderRadius:14, padding:'14px 36px', fontSize:16, fontWeight:700, color:'#fff', cursor:'pointer', marginTop:8 }
}

export default App