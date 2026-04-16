import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Bar, Line, Doughnut } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement,
  LineElement, BarElement, ArcElement, Title, Tooltip, Legend, Filler
} from 'chart.js'

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, Tooltip, Legend, Filler
)

const API_URL   = 'http://localhost:8000'
const MOBILE_BP = 768
const BERT_MIN_DELAY = 300
const BERT_MAX_DELAY = 700

function useMediaQuery(query) {
  const [matches, setMatches] = useState(
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false
  )
  useEffect(() => {
    const media = window.matchMedia(query)
    setMatches(media.matches)
    const listener = () => setMatches(media.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [query])
  return matches
}

const PARTICIPANT_COLORS = ['#00C7BE', '#BF5AF2', '#FF9F0A', '#30D158', '#FF375F']
const SPEEDS   = [1, 2, 5, 10, 20]
const FRAMERATES = [
  { label: 'Off', value: 0 }, { label: '2s', value: 2 }, { label: '5s', value: 5 },
  { label: '10s', value: 10 }, { label: '30s', value: 30 },
]

const tsToSec    = ts => ts ? new Date(ts).getTime() / 1000 : 0
const secToLabel = sec => {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60)
  return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
}
const bertDelay = () => BERT_MIN_DELAY + Math.random() * (BERT_MAX_DELAY - BERT_MIN_DELAY)

// ─── Toast ────────────────────────────────────────────────────────────────────
const Toast = ({ message, type, onClose }) => {
  useEffect(() => { const t = setTimeout(onClose, 2500); return () => clearTimeout(t) }, [onClose])
  const bg = { info:'#007AFF', success:'#34C759', error:'#FF3B30', warning:'#FF9500' }[type]
  return (
    <div style={{ background:bg, color:'#fff', padding:'7px 12px', borderRadius:8,
      marginBottom:6, fontSize:12, fontWeight:600, opacity:0.9,
      boxShadow:'0 2px 8px rgba(0,0,0,0.25)', animation:'slideIn 0.2s ease' }}>
      {message}
    </div>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────
export default function App() {
  const isMobile = useMediaQuery(`(max-width: ${MOBILE_BP}px)`)
  const isSmall  = useMediaQuery('(max-width: 480px)')

  // ── Data ─────────────────────────────────────────────────────────────────
  const [allTranscript, setAllTranscript] = useState([])
  const [participants,  setParticipants]  = useState([])
  const [loading, setLoading]             = useState(false)
  const [error,   setError]               = useState(null)
  const [toxicityThreshold, setToxicityThreshold] = useState(0.6)

  // ── Playback ──────────────────────────────────────────────────────────────
  const [playbackIndex, setPlaybackIndex] = useState(0)
  const [isPlaying,     setIsPlaying]     = useState(false)
  const [mode,             setMode]            = useState('live')
  const [joinOffset,       setJoinOffset]      = useState(0)
  const [meetingStatus,    setMeetingStatus]   = useState('not_started')
  const [liveSpeed,        setLiveSpeed]       = useState(1.0)
  const [liveTotalSec,     setLiveTotalSec]    = useState(0)
  const pollTimerRef = useRef(null)
  const [frameRate,         setFrameRate]      = useState(0)
  const [simOffset,         setSimOffset]      = useState(0)
  const simOffsetRef = useRef(0)
  const frameTimerRef = useRef(null)
  const liveTimerSync = useRef(null)
  const liveClockRef  = useRef(null)
  const [bertProcessing,  setBertProcessing] = useState(false)
  const [speed, setSpeed] = useState(5)
  const timerRef = useRef(null)
  const indexRef = useRef(0)
  const [wallSec, setWallSec] = useState(0)
  const wallRef  = useRef(0)
  const clockRef = useRef(null)

  // ── UI ────────────────────────────────────────────────────────────────────
  const [meetingList,       setMeetingList]     = useState([])
  const [selectedMeeting,   setSelectedMeeting] = useState('mtg001')
  const [showWidgetPanel,   setShowWidgetPanel] = useState(false)
  const [openSettings,      setOpenSettings]    = useState(null)
  const [toasts,            setToasts]          = useState([])
  const [showJoinBanner,    setShowJoinBanner]  = useState(false)

  const [visibleWidgets, setVisibleWidgets] = useState({
    messages:true, sentimentKPI:true, toxicityKPI:true, healthScore:true,
    sentimentDist:true, timelineSentiment:true, timelineToxicity:true,
    participantRoster:true, messageStream:true
  })

  const [widgetConfigs, setWidgetConfigs] = useState({
    messages:          { participantFilter:null },
    sentimentKPI:      { participantFilter:null },
    toxicityKPI:       { participantFilter:null },
    healthScore:       { participantFilter:null },
    sentimentDist:     { participantFilter:null },
    timelineSentiment: { participantFilter:null },
    timelineToxicity:  { participantFilter:null },
    participantRoster: { participantFilter:null },
    messageStream:     { participantFilter:null, limit:30 },
  })

  const toastCounter = useRef(0)
  const showToast = useCallback((msg, type='info') => {
    const id = ++toastCounter.current
    setToasts(p => [...p, { id, message: msg, type }])
  }, [])

  // ── playback helpers ──────────────────────────────────────────────────────
  const stopTimer = useCallback(() => {
    if (timerRef.current)  { clearTimeout(timerRef.current);  timerRef.current  = null }
  }, [])
  const stopClock = useCallback(() => {
    if (clockRef.current) { clearInterval(clockRef.current); clockRef.current = null }
  }, [])
  const stopLiveClock = useCallback(() => {
    if (liveClockRef.current) { clearInterval(liveClockRef.current); liveClockRef.current = null }
  }, [])
  const stopPollTimer = useCallback(() => {
    if (pollTimerRef.current) { clearInterval(pollTimerRef.current); pollTimerRef.current = null }
  }, [])
  const startLiveClock = useCallback(() => {
    if (liveClockRef.current) clearInterval(liveClockRef.current)
    liveClockRef.current = setInterval(() => {
      const sync = liveTimerSync.current
      if (!sync) return
      const elapsed = sync.wallAtSync + (Date.now() - sync.realAtSync) / 1000
      wallRef.current = elapsed
      setWallSec(elapsed)
    }, 100)
  }, [])

  const stopTimerRef = useRef(stopTimer)
  const stopClockRef  = useRef(stopClock)
  const startClockRef = useRef(null)
  useEffect(() => { stopTimerRef.current = stopTimer }, [stopTimer])
  useEffect(() => { stopClockRef.current = stopClock }, [stopClock])

  // ── pollBackend ───────────────────────────────────────────────────────────
  const pollBackend = useCallback(async (meetingId) => {
    try {
      const [rStatus, rData] = await Promise.all([
        fetch(`${API_URL}/meeting/${meetingId}/status`),
        fetch(`${API_URL}/meeting/${meetingId}/analysis`),
      ])
      if (!rStatus.ok || !rData.ok) return
      const [dStatus, dData] = await Promise.all([rStatus.json(), rData.json()])

      setMeetingStatus(dStatus.status)
      if (dStatus.total_seconds > 0) setLiveTotalSec(dStatus.total_seconds)

      const newTranscript = dData.transcript || []
      setAllTranscript(prev => {
        if (newTranscript.length > prev.length) return newTranscript
        return prev
      })

      if (dStatus.elapsed_seconds >= 0 && dStatus.status !== 'ended') {
        liveTimerSync.current = { wallAtSync: dStatus.elapsed_seconds, realAtSync: Date.now() }
      }

      if (dStatus.status === 'ended') {
        stopPollTimer(); stopLiveClock()
        setBertProcessing(false); setIsPlaying(false)
        liveTimerSync.current = null
        const totalSec = dStatus.total_seconds || 0
        wallRef.current = totalSec; setWallSec(totalSec)
      }
    } catch { /* silenzioso */ }
  }, [stopPollTimer, stopLiveClock])

  const loadMeeting = useCallback(async (meetingId) => {
    setLoading(true); setError(null)
    stopTimerRef.current(); stopClockRef.current(); stopPollTimer()
    indexRef.current = 0; wallRef.current = 0
    setPlaybackIndex(0); setWallSec(0); setIsPlaying(false)
    setMode('live'); setMeetingStatus('not_started'); setBertProcessing(false)
    setSimOffset(0); simOffsetRef.current = 0
    setShowJoinBanner(false); setAllTranscript([])

    try {
      const rP = await fetch(`${API_URL}/participants`)
      if (!rP.ok) throw new Error('participants error')
      const dP = await rP.json()
      setParticipants(dP.participants)

      const joinPct  = 0.2 + Math.random() * 0.4
      const startRes = await fetch(`${API_URL}/meeting/${meetingId}/start?speed=${liveSpeed}`, { method: 'POST' })
      if (!startRes.ok) throw new Error('start error')
      const startData = await startRes.json()
      const totalSec  = startData.total_seconds
      const joinSec   = Math.floor(totalSec * joinPct)
      await fetch(`${API_URL}/meeting/${meetingId}/start?speed=${liveSpeed}&join_offset=${joinSec}`, { method: 'POST' })

      liveTimerSync.current = { wallAtSync: 0, realAtSync: Date.now() }
      await pollBackend(meetingId)
      setMeetingStatus('active'); setIsPlaying(true)
      setShowJoinBanner(true)
      setTimeout(() => setShowJoinBanner(false), 5000)
    } catch {
      setError('Impossibile caricare il meeting')
      showToast('Errore caricamento', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast, stopPollTimer, pollBackend, liveSpeed])

  useEffect(() => {
    fetch(`${API_URL}/meetings`).then(r=>r.json()).then(d=>setMeetingList(d.meetings||[])).catch(()=>{})
    // Legge la soglia di tossicità dal backend (configurabile via env TOXICITY_THRESHOLD)
    fetch(`${API_URL}/health`).then(r=>r.json()).then(d=>{
      if (d.toxicity_threshold != null) setToxicityThreshold(d.toxicity_threshold)
    }).catch(()=>{})
  }, [])
  useEffect(() => { loadMeeting(selectedMeeting) }, [selectedMeeting, loadMeeting])

  useEffect(() => {
    if (mode !== 'live' || meetingStatus === 'ended' || meetingStatus === 'not_started') {
      stopPollTimer()
      if (meetingStatus === 'ended') { setBertProcessing(false); stopLiveClock() }
      return
    }
    if (!liveTimerSync.current) {
      liveTimerSync.current = { wallAtSync: wallRef.current, realAtSync: Date.now() }
    }
    startLiveClock()
    const interval = frameRate > 0 ? frameRate * 1000 : 3000
    stopPollTimer()
    pollTimerRef.current = setInterval(() => pollBackend(selectedMeeting), interval)
    return () => { stopPollTimer(); stopLiveClock() }
  }, [mode, meetingStatus, frameRate, selectedMeeting, pollBackend, stopPollTimer, startLiveClock, stopLiveClock])

  // ── playback engine ───────────────────────────────────────────────────────
  const scheduleNext = useCallback((idx, transcript, spd, isLive) => {
    if (idx >= transcript.length) {
      setBertProcessing(false)
      if (transcript.length > 0) {
        const exact = tsToSec(transcript[transcript.length - 1].created_at) - tsToSec(transcript[0].created_at)
        wallRef.current = exact; setWallSec(exact)
      }
      setIsPlaying(false); return
    }
    const gap = transcript[idx + 1]
      ? tsToSec(transcript[idx + 1].created_at) - tsToSec(transcript[idx].created_at) : 1
    const naturalDelay = Math.max(80, (gap * 1000) / spd)
    const delay = isLive ? naturalDelay + bertDelay() : naturalDelay
    timerRef.current = setTimeout(() => {
      setBertProcessing(false)
      const next = idx + 1; indexRef.current = next; setPlaybackIndex(next)
      if (transcript[next-1])
        wallRef.current = tsToSec(transcript[next-1].created_at) - tsToSec(transcript[0].created_at)
      scheduleNext(next, transcript, spd, isLive)
    }, delay)
  }, [])

  const startClock = useCallback((spd) => {
    stopClock()
    clockRef.current = setInterval(() => { wallRef.current += 0.1 * spd; setWallSec(wallRef.current) }, 100)
  }, [stopClock])
  useEffect(() => { startClockRef.current = startClock }, [startClock])

  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) { stopClock() }
      else if (isPlaying) { startClock(mode === 'live' ? 1 : speed) }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [isPlaying, mode, speed, stopClock, startClock])

  useEffect(() => {
    if (isPlaying && allTranscript.length > 0) {
      if (indexRef.current >= allTranscript.length) {
        indexRef.current = mode === 'review' ? 0 : joinOffset
        wallRef.current  = mode === 'review' ? 0 : (
          allTranscript[joinOffset] ? tsToSec(allTranscript[joinOffset].created_at) - tsToSec(allTranscript[0].created_at) : 0
        )
        setPlaybackIndex(indexRef.current); setWallSec(wallRef.current)
      }
      if (mode === 'live') return
      scheduleNext(indexRef.current, allTranscript, speed, false)
      startClock(speed)
    } else { stopTimer(); stopClock(); setBertProcessing(false) }
    return () => { stopTimer(); stopClock(); setBertProcessing(false) }
  }, [isPlaying, allTranscript, speed, mode, joinOffset, scheduleNext, startClock, stopTimer, stopClock])

  // ── handlers ─────────────────────────────────────────────────────────────
  const handlePlayPause = () => { if (mode === 'review') setIsPlaying(p => !p) }
  const enterReviewMode = () => {
    stopTimer(); stopClock(); stopPollTimer(); setIsPlaying(false)
    setBertProcessing(false)
    indexRef.current = 0; wallRef.current = 0
    setPlaybackIndex(0); setWallSec(0)
    setMode('review'); setSpeed(5)
  }
  const handleReset = () => {
    if (mode !== 'review') return
    stopTimer(); stopClock(); setIsPlaying(false)
    indexRef.current = 0; wallRef.current = 0
    setPlaybackIndex(0); setWallSec(0)
  }
  const handleSpeedChange = s => {
    if (mode !== 'review') return
    setSpeed(s)
    if (isPlaying) { stopTimer(); stopClock(); setIsPlaying(false); setTimeout(() => setIsPlaying(true), 30) }
  }

  // ── export ────────────────────────────────────────────────────────────────
  const exportJSON = () => {
    const data = { meeting_id:selectedMeeting, exported_at:new Date().toISOString(), mode, transcript:allTranscript, stats:calcStats(allTranscript) }
    const blob  = new Blob([JSON.stringify(data, null, 2)], { type:'application/json' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download:`${selectedMeeting}_${new Date().toISOString().split('T')[0]}.json` })
    a.click(); URL.revokeObjectURL(a.href)
  }
  const exportCSV = () => {
    const headers = ['timestamp','participant','text','sentiment_label','sentiment_score','toxicity_score','is_toxic']
    const rows = allTranscript.map(e => [
      e.created_at, e.participant_name, `"${e.transcribed_text.replace(/"/g,'""')}"`,
      e.sentiment.label, e.sentiment.score, e.toxicity.toxicity_score, e.toxicity.is_toxic
    ])
    const blob = new Blob([[headers.join(','), ...rows.map(r=>r.join(','))].join('\n')], { type:'text/csv;charset=utf-8;' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download:`${selectedMeeting}_${new Date().toISOString().split('T')[0]}.csv` })
    a.click(); URL.revokeObjectURL(a.href)
  }

  // ── computed ──────────────────────────────────────────────────────────────
  const liveTranscript = mode === 'live' ? allTranscript : allTranscript.slice(0, playbackIndex)
  const total      = allTranscript.length
  const baseTs     = total > 0 ? tsToSec(allTranscript[0].created_at) : 0
  const _totalSecFromTs = total > 0 ? tsToSec(allTranscript[total-1].created_at) - baseTs : 0
  const totalSec   = mode === 'live' && liveTotalSec > 0 ? liveTotalSec : _totalSecFromTs
  const progressPct = mode === 'review'
    ? (totalSec > 0 ? Math.min((wallSec / totalSec) * 100, 100) : 0)
    : (total > 0 ? Math.min((allTranscript.length / total) * 100, 100) : 0)
  const isFinished = mode === 'live' ? meetingStatus === 'ended' : playbackIndex >= total && total > 0
  const liveEnded  = meetingStatus === 'ended' && mode === 'live'

  // ── helpers ───────────────────────────────────────────────────────────────
  const calcStats = tr => {
    if (!tr?.length) return {
      total_messages:0,
      sentiment:{ distribution:{ positive:0, neutral:0, negative:0 }, average_score:0, positive_ratio:0 },
      toxicity: { toxic_count:0, toxic_ratio:0, severity_distribution:{ low:0, medium:0, high:0 }, average_toxicity_score:0 }
    }
    let sc=0, tx=0, tc=0
    const d={ positive:0, neutral:0, negative:0 }, sv={ low:0, medium:0, high:0 }
    tr.forEach(e => {
      d[e.sentiment.label]++; sc += e.sentiment.score
      if (e.toxicity.is_toxic) tc++; sv[e.toxicity.severity]++; tx += e.toxicity.toxicity_score
    })
    const n = tr.length
    return {
      total_messages:n,
      sentiment:{ distribution:d, average_score:sc/n, positive_ratio:d.positive/n },
      toxicity: { toxic_count:tc, toxic_ratio:tc/n, severity_distribution:sv, average_toxicity_score:tx/n }
    }
  }

  const toggleWidget       = id => setVisibleWidgets(p => ({ ...p, [id]: !p[id] }))
  const updateWidgetConfig = (id,u) => setWidgetConfigs(p => ({ ...p, [id]:{ ...p[id], ...u } }))

  const getFiltered = id => {
    const pf = widgetConfigs[id]?.participantFilter
    if (!pf) return liveTranscript
    const p = participants.find(x => x.id === pf)
    return p ? liveTranscript.filter(e => e.participant_name === p.name) : liveTranscript
  }
  const F    = id  => getFiltered(id)
  const S_id = id  => calcStats(F(id))
  const getParticipantStats = () => memoParticipantStats
  const calcPolarity = stats => {
    if (stats.total_messages === 0) return null
    const { positive, negative } = stats.sentiment.distribution
    return ((positive - negative) / stats.total_messages)
  }
  const memoParticipantStats = useMemo(
    () => participants.map(p => ({ ...p, stats: calcStats(liveTranscript.filter(e => e.participant_name === p.name)) })),
    [liveTranscript, participants]
  )

  // ── widget sections ───────────────────────────────────────────────────────
  const SECTIONS = [
    { title:'KPI', items:[
      { id:'messages',    name:'Messaggi',           desc:'Contatore messaggi ricevuti.' },
      { id:'sentimentKPI',name:'Sentiment %',        desc:'Distribuzione positivo/neutro/negativo.' },
      { id:'toxicityKPI', name:'Tossicità',          desc:'Conteggio e % messaggi tossici.' },
      { id:'healthScore', name:'Sentiment Polarity', desc:'Indice [-1,+1]: (positivi-negativi)/totale.' },
    ]},
    { title:'Grafici', items:[
      { id:'sentimentDist',     name:'Distribuzione Sentiment', desc:'Barra pos/neu/neg in percentuale.' },
      { id:'timelineSentiment', name:'Timeline Sentiment',      desc:'Polarity per ogni messaggio nel tempo.' },
      { id:'timelineToxicity',  name:'Timeline Tossicità',      desc:'Probabilità di tossicità per partecipante.' },
    ]},
    { title:'Altro', items:[
      { id:'participantRoster', name:'Partecipanti',    desc:'Distribuzione sentiment per partecipante.' },
      { id:'messageStream',     name:'Stream Messaggi', desc:'Feed messaggi con badge sentiment/tossicità.' },
    ]},
  ]

  // ── widget builder ────────────────────────────────────────────────────────
  const wgt = (id, title, wide, children) =>
    visibleWidgets[id] !== false ? (
      <Wgt key={id} id={id} title={title} wide={wide}
        cfg={widgetConfigs[id]} participants={participants}
        onCfg={u => updateWidgetConfig(id, u)}
        open={openSettings} setOpen={setOpenSettings}>
        {children}
      </Wgt>
    ) : null

  // Tutti i widget visibili nella dashboard unica (nessuna navigazione per vista)
  const buildWidgets = () => {
    const polarity = calcPolarity(S_id('healthScore'))
    const wMessages = wgt('messages','Messaggi',false,
      <><div style={S.kpiVal}>{F('messages').length}</div><div style={S.kpiLab}>messaggi ricevuti</div></>)
    const wSentKPI  = wgt('sentimentKPI','Sentiment',false,    <SentimentKPI stats={S_id('sentimentKPI')} />)
    const wToxKPI   = wgt('toxicityKPI','Tossicità',false,     <ToxicityKPI  stats={S_id('toxicityKPI')} threshold={toxicityThreshold} />)
    const wHealth   = wgt('healthScore','Sentiment Polarity Index',false,(() => {
      if (polarity === null) return <Empty />
      const color = polarity>=0.3?'#34C759':polarity<=-0.3?'#FF3B30':'#FF9500'
      return (
        <>
          <div style={{ ...S.kpiVal, color, fontSize:38, fontVariantNumeric:'tabular-nums' }}>
            {polarity >= 0 ? '+' : ''}{polarity.toFixed(2)}
          </div>
          <div style={{ fontSize:11, color, fontWeight:700, textTransform:'uppercase', marginTop:2 }}>
            {polarity >= 0.3 ? 'Positivo' : polarity <= -0.3 ? 'Negativo' : 'Neutro'}
          </div>
          <div style={S.kpiLab}>(positivi − negativi) / totale · range [−1, +1]</div>
        </>
      )
    })())
    const wSentDist = wgt('sentimentDist','Distribuzione Sentiment',true, <SentimentDistChart stats={S_id('sentimentDist')} />)
    const wTimeSent = wgt('timelineSentiment',
      'Timeline Sentiment — classificazione per messaggio nel tempo', true,
      <TimelineChart
        messages={F('timelineSentiment')}
        metric="sentiment"
        yLabel="Categoria modello nlptown"
        participants={participants}
        participantColors={PARTICIPANT_COLORS}
        meetingStartTime={allTranscript[0]?.created_at}
      />
    )

    const wTimeTox = wgt('timelineToxicity',
      'Timeline Tossicità — probabilità per partecipante', true,
      <TimelineChart
        messages={F('timelineToxicity')}
        metric="toxicity"
        yLabel="Probabilità tossicità gravitee-io [0–100%]"
        participants={participants}
        participantColors={PARTICIPANT_COLORS}
        meetingStartTime={allTranscript[0]?.created_at}
      />
    )

    const wRoster   = wgt('participantRoster','Partecipanti',true,
      <ParticipantRoster stats={getParticipantStats()} participantColors={PARTICIPANT_COLORS} />)
    const wStream   = wgt('messageStream','Stream Messaggi',true,
      <MessageStream messages={F('messageStream')} limit={widgetConfigs.messageStream?.limit||30}
        participantColors={PARTICIPANT_COLORS} participants={participants}
        meetingStartTime={allTranscript[0]?.created_at} />)
    return [wMessages, wHealth, wSentKPI, wToxKPI, wSentDist, wTimeSent, wTimeTox, wStream, wRoster].filter(Boolean)
  }

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div style={S.app}>
      {/* Toasts */}
      <div style={{ position:'fixed', top:isMobile?10:20, right:isMobile?10:20, zIndex:1000, display:'flex', flexDirection:'column', alignItems:'flex-end' }}>
        {toasts.map(t => <Toast key={t.id} {...t} onClose={() => setToasts(p => p.filter(x => x.id !== t.id))} />)}
      </div>

      <div style={{ display:'flex', minHeight:'100vh' }}>
        <div style={{ flex:1, minWidth:0, paddingBottom:0 }}>

          {/* ── Header ─────────────────────────────────────────────────── */}
          <div style={S.header}>
            <div style={{ ...S.hRow, flexDirection: isMobile ? 'column' : 'row' }}>

              <div style={S.hLeft}>
                {isMobile && <div style={S.logo}>MI</div>}
                <div>
                  <h1 style={S.title}>Meeting Intelligence</h1>
                  <p style={S.subtitle}>{selectedMeeting.toUpperCase()}</p>
                </div>
                {meetingList.length > 1 && (
                  <select value={selectedMeeting} onChange={e => setSelectedMeeting(e.target.value)} style={S.select}>
                    {meetingList.map(m => (
                      <option key={m.id} value={m.id}>
                        {m.id.toUpperCase()} · {new Date(m.date).toLocaleDateString('it-IT',{day:'2-digit',month:'short'})}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                {mode === 'live' && !liveEnded && (
                  <>
                    <div style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
                      background:'rgba(255,59,48,0.15)', border:'0.5px solid rgba(255,59,48,0.4)', borderRadius:8 }}>
                      <span style={{ width:8, height:8, borderRadius:'50%', background:'#FF3B30', animation:'pulse 1.5s ease-in-out infinite', flexShrink:0 }} />
                      <span style={{ fontSize:12, fontWeight:700, color:'#FF3B30', textTransform:'uppercase', letterSpacing:'0.5px' }}>Live</span>
                    </div>
                    <div style={{ display:'flex', alignItems:'center', gap:8, background:'rgba(255,255,255,0.05)', borderRadius:8, padding:'4px 10px' }}>
                      <span style={{ fontSize:11, color:'#8e8e93', fontWeight:600 }}>POLL</span>
                      <select value={frameRate} onChange={e => setFrameRate(Number(e.target.value))}
                        style={{ background:'none', border:'none', color:'#fff', fontSize:12, fontWeight:700, outline:'none', cursor:'pointer' }}>
                        {FRAMERATES.map(f => <option key={f.value} value={f.value} style={{ background:'#1c1c1e' }}>{f.label}</option>)}
                      </select>
                    </div>
                    <span style={{ fontSize:13, fontWeight:700, fontVariantNumeric:'tabular-nums', color:'#fff', marginLeft:4 }}>
                      {secToLabel(wallSec)}{totalSec > 0 ? ` / ${secToLabel(totalSec)}` : ''}
                    </span>
                  </>
                )}
                {mode === 'review' && (
                  <>
                    <button onClick={handlePlayPause} style={{ ...S.btn, background: isPlaying ? '#FF9500' : '#34C759', width:40, padding:0, fontSize:16 }}>
                      {isPlaying ? '⏸' : '▶'}
                    </button>
                    <button onClick={handleReset} style={{ ...S.btn, width:40, padding:0, fontSize:16 }}>⏮</button>
                    <div style={{ display:'flex', gap:2, background:'rgba(255,255,255,0.07)', borderRadius:8, padding:3 }}>
                      {SPEEDS.map(s => (
                        <button key={s} onClick={() => handleSpeedChange(s)}
                          style={{ border:'none', borderRadius:5, padding:'3px 8px', fontSize:12, cursor:'pointer',
                            background: speed===s ? '#007AFF' : 'transparent',
                            color: speed===s ? '#fff' : '#8e8e93', fontWeight: speed===s ? 700 : 500 }}>
                          {s}×
                        </button>
                      ))}
                    </div>
                    <span style={{ fontSize:13, fontWeight:700, fontVariantNumeric:'tabular-nums', color:'#fff' }}>
                      {secToLabel(Math.min(wallSec, totalSec))} / {secToLabel(totalSec)}
                    </span>
                  </>
                )}
                <button onClick={() => setShowWidgetPanel(v => !v)} style={S.btn}>⚙️</button>
              </div>
            </div>

            {/* Progress bar */}
            <div style={{ height:3, background:'rgba(255,255,255,0.07)' }}>
              <div style={{ height:'100%', width:`${Math.min(progressPct,100)}%`, transition:'width 0.3s ease',
                background: isFinished ? '#34C759' : isPlaying ? '#007AFF' : '#636366' }} />
            </div>

            {/* Status row */}
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'3px 16px 6px', fontSize:11 }}>
              <span style={{ color:'#636366' }}>
                {mode === 'live'
                  ? `${liveTranscript.length} messaggi ricevuti${joinOffset > 0 ? ` · entrato al msg ${joinOffset+1}/${total}` : ''}`
                  : `${playbackIndex} / ${total} messaggi`}
              </span>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ color: isPlaying ? '#007AFF' : isFinished ? '#34C759' : '#636366' }}>
                  {mode==='live'  && isPlaying   && '● In diretta'}
                  {mode==='live'  && liveEnded   && '✓ Meeting concluso'}
                  {mode==='review'&& isPlaying   && `▶ Revisione ${speed}×`}
                  {mode==='review'&& !isPlaying  && !isFinished && '⏸ In pausa'}
                  {mode==='review'&& isFinished  && '✓ Fine revisione'}
                </span>
              </div>
            </div>

            {liveEnded && (
              <div style={{ maxWidth:1400, margin:'0 auto', padding:'8px 16px 12px', display:'flex', gap:10, alignItems:'center', flexWrap:'wrap', borderTop:'0.5px solid rgba(255,255,255,0.08)' }}>
                <span style={{ fontSize:13, fontWeight:600, color:'#fff' }}>Meeting concluso.</span>
                <button onClick={enterReviewMode} style={{ ...S.btn, background:'#007AFF' }}>↩ Rivedi dall'inizio</button>
                <button onClick={exportJSON} style={{ ...S.btn, background:'#5856D6' }}>📥 JSON</button>
                <button onClick={exportCSV}  style={{ ...S.btn, background:'#5856D6' }}>📊 CSV</button>
              </div>
            )}
            {mode==='review' && isFinished && (
              <div style={{ maxWidth:1400, margin:'0 auto', padding:'8px 16px 12px', display:'flex', gap:8, alignItems:'center' }}>
                <span style={{ fontSize:12, color:'#8e8e93' }}>Scarica i dati:</span>
                <button onClick={exportJSON} style={{ ...S.btn, background:'#5856D6' }}>📥 JSON</button>
                <button onClick={exportCSV}  style={{ ...S.btn, background:'#5856D6' }}>📊 CSV</button>
              </div>
            )}
          </div>

          {showJoinBanner && joinOffset > 0 && (
            <div style={{ margin:'12px 16px', padding:'10px 14px', background:'rgba(0,122,255,0.1)', border:'0.5px solid rgba(0,122,255,0.3)', borderRadius:10, fontSize:13, color:'#007AFF', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              <span>ℹ️ Sei entrato con il meeting in corso al messaggio <strong>{joinOffset+1}/{total}</strong>.</span>
              <button onClick={() => setShowJoinBanner(false)} style={{ background:'none', border:'none', color:'#007AFF', cursor:'pointer', fontSize:16, padding:'0 4px' }}>✕</button>
            </div>
          )}

          {error && (
            <div style={{ margin:16, padding:'12px 16px', background:'rgba(255,59,48,0.15)', border:'0.5px solid rgba(255,59,48,0.3)', borderRadius:10, color:'#FF3B30', fontSize:14 }}>
              ⚠ {error}
            </div>
          )}

          {loading && (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', height:'60vh', gap:16 }}>
              <div style={{ width:32, height:32, border:'3px solid rgba(255,255,255,0.1)', borderTop:'3px solid #007AFF', borderRadius:'50%', animation:'spin 1s linear infinite' }} />
              <p style={{ color:'#8e8e93', fontSize:14 }}>Connessione al meeting…</p>
            </div>
          )}

          {!loading && mode==='review' && playbackIndex===0 && !isPlaying && (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', minHeight:'60vh', gap:16, padding:24 }}>
              <div style={{ fontSize:48, color:'#3a3a3c' }}>↩</div>
              <div style={{ fontSize:20, fontWeight:700 }}>Revisione</div>
              <div style={{ fontSize:14, color:'#8e8e93', textAlign:'center', lineHeight:1.7 }}>
                {total} messaggi totali · {secToLabel(totalSec)} durata<br/>
                Premi <strong>Play</strong> e scegli la velocità
              </div>
              <button onClick={handlePlayPause} style={{ ...S.btn, background:'#007AFF', padding:'14px 36px', fontSize:16, fontWeight:700, borderRadius:14 }}>
                ▶ Inizia Revisione
              </button>
            </div>
          )}

          {!loading && liveTranscript.length > 0 && (
            <div style={{ ...S.grid, gridTemplateColumns: isSmall ? '1fr' : isMobile ? 'repeat(2, minmax(140px, 1fr))' : 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {buildWidgets()}
            </div>
          )}
        </div>
      </div>

      {/* ── Customize Panel ───────────────────────────────────────────────── */}
      {showWidgetPanel && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.5)', zIndex:200, display:'flex', justifyContent:'flex-end' }}
          onClick={() => setShowWidgetPanel(false)}>
          <div style={{ width:'clamp(300px,90vw,400px)', height:'100%', background:'#1c1c1e', borderLeft:'0.5px solid rgba(255,255,255,0.1)', display:'flex', flexDirection:'column' }}
            onClick={e => e.stopPropagation()}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'18px 20px', borderBottom:'0.5px solid rgba(255,255,255,0.08)' }}>
              <span style={{ fontSize:16, fontWeight:700 }}>Personalizza dashboard</span>
              <button onClick={() => setShowWidgetPanel(false)} style={{ background:'none', border:'none', color:'#007AFF', cursor:'pointer', fontSize:14 }}>Chiudi</button>
            </div>
            <div style={{ flex:1, overflowY:'auto' }}>
              {SECTIONS.map(sec => (
                <div key={sec.title}>
                  <div style={{ fontSize:11, fontWeight:600, color:'#636366', textTransform:'uppercase', letterSpacing:'0.8px', padding:'14px 20px 6px' }}>{sec.title}</div>
                  {sec.items.map((w,wi) => (
                    <div key={w.id}>
                      <div style={{ display:'flex', alignItems:'flex-start', padding:'12px 20px', gap:10 }}>
                        <div style={{ flex:1 }}>
                          <div style={{ fontSize:14, fontWeight:500, color:'#fff', marginBottom:2 }}>{w.name}</div>
                          <div style={{ fontSize:12, color:'#8e8e93' }}>{w.desc}</div>
                        </div>
                        <button
                          style={{ border:'none', borderRadius:7, padding:'5px 12px', cursor:'pointer', fontSize:12, fontWeight:600, flexShrink:0,
                            background: visibleWidgets[w.id]!==false ? '#34C759' : '#3a3a3c',
                            color:       visibleWidgets[w.id]!==false ? '#fff'    : '#8e8e93' }}
                          onClick={() => toggleWidget(w.id)}>
                          {visibleWidgets[w.id]!==false ? 'ON' : 'OFF'}
                        </button>
                      </div>
                      {wi < sec.items.length-1 && <div style={{ height:'0.5px', background:'rgba(255,255,255,0.06)', margin:'0 20px' }} />}
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div style={{ padding:'10px 20px', borderTop:'0.5px solid rgba(255,255,255,0.08)', fontSize:12, color:'#636366', textAlign:'center' }}>
              {(() => {
                const ids = SECTIONS.flatMap(s => s.items.map(i => i.id))
                const active = ids.filter(id => visibleWidgets[id] !== false).length
                return `${active} / ${ids.length} widget attivi`
              })()}
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideIn { from { transform:translateX(300px); opacity:0 } to { transform:translateX(0); opacity:1 } }
        @keyframes spin    { to   { transform:rotate(360deg) } }
        @keyframes pulse   { 0%,100% { opacity:1 } 50% { opacity:0.3 } }
        * { box-sizing:border-box }
      `}</style>
    </div>
  )
}

// ─── Widget Wrapper ───────────────────────────────────────────────────────────
function Wgt({ id, title, children, wide, cfg, participants, onCfg, open, setOpen }) {
  const isOpen = open === id
  return (
    <div style={{ background:'rgba(255,255,255,0.05)', borderRadius:16,
      border:'0.5px solid rgba(255,255,255,0.1)', overflow:'hidden',
      ...(wide ? { gridColumn:'1 / -1' } : {}) }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'10px 12px 0' }}>
        <span style={{ fontSize:11, fontWeight:600, color:'#8e8e93', textTransform:'uppercase', letterSpacing:'0.5px' }}>{title}</span>
        <button onClick={() => setOpen(isOpen ? null : id)}
          style={{ background:'none', border:'none', color:'#636366', cursor:'pointer', fontSize:16, lineHeight:1 }}>
          {isOpen ? '✕' : '⋯'}
        </button>
      </div>
      {isOpen && (
        <div style={{ margin:'8px 14px', padding:'8px 12px', background:'rgba(0,0,0,0.3)', borderRadius:8, display:'flex', alignItems:'center', gap:8 }}>
          <span style={{ fontSize:12, color:'#8e8e93' }}>Partecipante</span>
          <select value={cfg?.participantFilter||''} onChange={e => onCfg({ participantFilter: e.target.value||null })}
            style={{ flex:1, background:'rgba(255,255,255,0.1)', border:'0.5px solid rgba(255,255,255,0.15)', borderRadius:6, color:'#fff', padding:'3px 8px', fontSize:12 }}>
            <option value="">Tutti</option>
            {participants.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
      <div style={{ padding:'8px 12px 12px' }}>{children}</div>
    </div>
  )
}

// ─── SentimentKPI ─────────────────────────────────────────────────────────────
function SentimentKPI({ stats }) {
  const n = stats.total_messages
  if (n===0) return <Empty />
  const { positive, neutral, negative } = stats.sentiment.distribution
  const posPct = Math.round(positive/n*100)
  const neuPct = Math.round(neutral/n*100)
  const negPct = Math.round(negative/n*100)
  return (
    <div>
      <div style={{ display:'flex', height:8, borderRadius:4, overflow:'hidden', marginBottom:8 }}>
        <div style={{ width:`${posPct}%`, background:'#34C759', transition:'width 0.4s' }} />
        <div style={{ width:`${neuPct}%`, background:'#FFCC00', transition:'width 0.4s' }} />
        <div style={{ width:`${negPct}%`, background:'#FF3B30', transition:'width 0.4s' }} />
      </div>
      <div style={{ display:'flex', gap:10, fontSize:11, flexWrap:'wrap' }}>
        <span style={{ color:'#34C759' }}>● Positivi: {positive} ({posPct}%)</span>
        <span style={{ color:'#FFCC00' }}>● Neutri: {neutral} ({neuPct}%)</span>
        <span style={{ color:'#FF3B30' }}>● Negativi: {negative} ({negPct}%)</span>
      </div>
    </div>
  )
}

// ─── ToxicityKPI ──────────────────────────────────────────────────────────────
// Soglia letta dal backend via /health (configurabile con env TOXICITY_THRESHOLD).
function ToxicityKPI({ stats, threshold }) {
  const n = stats.total_messages
  if (n===0) return <Empty />
  const { toxic_count, toxic_ratio } = stats.toxicity
  const pct   = Math.round(toxic_ratio*100)
  const color = pct>20 ? '#FF3B30' : pct>5 ? '#FF9500' : '#34C759'
  const threshPct = Math.round((threshold ?? 0.6) * 100)
  return (
    <div>
      <div style={{ fontSize:36, fontWeight:700, color, lineHeight:1 }}>{toxic_count}</div>
      <div style={{ fontSize:12, color:'#8e8e93', marginBottom:12 }}>messaggi tossici su {n} ({pct}%)</div>
      <div style={{ fontSize:11, color:'#636366' }}>
        Tossico se probabilità &gt; {threshPct}%
      </div>
    </div>
  )
}

// ─── SentimentDistChart ───────────────────────────────────────────────────────
function SentimentDistChart({ stats }) {
  const n = stats.total_messages
  if (n===0) return <Empty />
  const { positive, neutral, negative } = stats.sentiment.distribution
  return (
    <div style={{ height:130 }}>
      <Bar
        data={{ labels:['Distribuzione messaggi'], datasets:[
          { label:`Positivi (${Math.round(positive/n*100)}%)`, data:[positive], backgroundColor:'#34C759', borderRadius:5 },
          { label:`Neutri (${Math.round(neutral/n*100)}%)`,    data:[neutral],  backgroundColor:'#FFCC00', borderRadius:5 },
          { label:`Negativi (${Math.round(negative/n*100)}%)`, data:[negative], backgroundColor:'#FF3B30', borderRadius:5 },
        ]}}
        options={{ indexAxis:'y', responsive:true, maintainAspectRatio:false, animation:{ duration:250 },
          plugins:{ legend:{ display:true, position:'bottom', labels:{ color:'#8e8e93', font:{ size:11 }, boxWidth:12 } },
            tooltip:{ backgroundColor:'rgba(28,28,30,0.95)', callbacks:{ label:ctx=>`${ctx.dataset.label}: ${ctx.parsed.x} messaggi` } } },
          scales:{
            x:{ stacked:true, grid:{ color:'rgba(255,255,255,0.05)' }, ticks:{ color:'#8e8e93' },
              title:{ display:true, text:'N. messaggi', color:'#636366', font:{ size:10 } } },
            y:{ stacked:true, display:false }
          } }}
      />
    </div>
  )
}

// ─── TimelineChart ────────────────────────────────────────────────────────────
// sentiment: classificazione categorica nel tempo
//            asse Y = {negativo, neutrale, positivo} (discreto)
//            overlay di linee, una per partecipante
// toxicity:  linea probabilità softmax del modello gravitee-io [0-100%]
function TimelineChart({ messages, metric, yLabel, participants = [], participantColors = [], meetingStartTime }) {
  if (!messages?.length) return <Empty />
 
  // ── Asse X: tempo relativo dall'INIZIO DEL MEETING ─────────────
  // Ancorato a meetingStartTime così i timestamp non cambiano
  // quando si filtra per singolo partecipante.
  const base = new Date(meetingStartTime || messages[0].created_at).getTime()
  const fmt  = ts => {
    const s = Math.max(0, (new Date(ts).getTime() - base) / 1000)
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`
  }
 
  // ═══════════════════════════════════════════════════════════════
  // BRANCH SENTIMENT: classificazione categorica nel tempo
  // ═══════════════════════════════════════════════════════════════
  if (metric === 'sentiment') {
    // Mappatura label → posizione Y (solo per il posizionamento grafico)
    const LABEL_Y = { negative: -1, neutral: 0, positive: 1 }
    const LABEL_COLOR = { negative: '#FF3B30', neutral: '#FFCC00', positive: '#34C759' }
 
    // Nomi dei partecipanti presenti
    const participantNames = participants.length
      ? participants.map(p => p.name)
      : [...new Set(messages.map(m => m.participant_name))]
 
    const isMultiParticipant = participantNames.length > 1
      && new Set(messages.map(m => m.participant_name)).size > 1
 
    // Mapping di ogni messaggio in un punto
    const pts = messages.map(m => ({
      lbl:   fmt(m.created_at),
      nick:  m.participant_name,
      text:  m.transcribed_text,
      label: m.sentiment.label,
      y:     LABEL_Y[m.sentiment.label] ?? 0,
    }))
 
    // Etichette X sparse (non una per ogni messaggio)
    const step  = Math.max(1, Math.floor(messages.length / 10))
    const xLbls = pts.map((p, i) =>
      (i === 0 || i === pts.length - 1 || i % step === 0) ? p.lbl : ''
    )
 
    // Dataset builder: una linea per partecipante quando multi, singola altrimenti
    const datasets = isMultiParticipant
      ? participantNames.map((name, i) => {
          const color = participantColors[i % participantColors.length] || '#888'
          return {
            label: name,
            data: pts.map(p => p.nick === name ? p.y : null),
            borderColor: color,
            backgroundColor: color + '20',
            borderWidth: 1.5,
            // Colore punto = categoria, bordo punto = partecipante
            pointRadius: 5,
            pointHoverRadius: 8,
            pointBackgroundColor: pts.map(p =>
              p.nick === name ? LABEL_COLOR[p.label] : 'transparent'
            ),
            pointBorderColor: pts.map(p =>
              p.nick === name ? color : 'transparent'
            ),
            pointBorderWidth: 2,
            fill: false,
            tension: 0,          // linee dritte tra punti (step-like feeling)
            spanGaps: true,
            stepped: false,
          }
        })
      : [{
          label: participantNames[0] || 'Sentiment',
          data: pts.map(p => p.y),
          borderColor: '#636366',
          backgroundColor: 'rgba(100,100,100,0.1)',
          borderWidth: 1.5,
          pointRadius: 5,
          pointHoverRadius: 8,
          pointBackgroundColor: pts.map(p => LABEL_COLOR[p.label]),
          pointBorderColor: pts.map(p => LABEL_COLOR[p.label]),
          pointBorderWidth: 2,
          fill: false,
          tension: 0,
        }]
 
    return (
      <div style={{ height: 300, position: 'relative' }}>
        <Line
          data={{ labels: xLbls, datasets }}
          options={{
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 150 },
            interaction: { mode: 'nearest', axis: 'x', intersect: false },
            plugins: {
              legend: {
                display: isMultiParticipant,
                position: 'top',
                labels: { color: '#8e8e93', font: { size: 11 }, boxWidth: 12, padding: 8 },
              },
              tooltip: {
                backgroundColor: 'rgba(28,28,30,0.95)',
                callbacks: {
                  title: items => {
                    const p = pts[items[0].dataIndex]
                    return `${p.lbl} · ${p.nick}`
                  },
                  label: ctx => {
                    const p = pts[ctx.dataIndex]
                    const emoji = p.label === 'positive' ? '🟢'
                                : p.label === 'negative' ? '🔴'
                                : '🟡'
                    return `${emoji} ${p.label.toUpperCase()}`
                  },
                  afterLabel: ctx => {
                    const t = pts[ctx.dataIndex].text
                    return t.length > 70 ? t.slice(0, 70) + '…' : t
                  },
                },
              },
            },
            scales: {
              x: {
                grid: { color: 'rgba(255,255,255,0.05)' },
                ticks: { color: '#8e8e93', maxRotation: 0 },
                title: {
                  display: true, text: "Minuti dall'inizio del meeting",
                  color: '#636366', font: { size: 10 }
                },
              },
              y: {
                min: -1.3, max: 1.3,
                grid: { color: 'rgba(255,255,255,0.05)' },
                ticks: {
                  color: '#8e8e93',
                  stepSize: 1,
                  callback: v => {
                    if (v ===  1) return 'Positivo'
                    if (v ===  0) return 'Neutrale'
                    if (v === -1) return 'Negativo'
                    return ''
                  },
                },
                title: {
                  display: true, text: 'Categoria modello nlptown',
                  color: '#636366', font: { size: 10 }
                },
              },
            },
          }}
        />
      </div>
    )
  }
 
  // ═══════════════════════════════════════════════════════════════
  // BRANCH TOXICITY: linea probabilità (invariato)
  // ═══════════════════════════════════════════════════════════════
  const pts = messages.map(m => ({
    lbl:      fmt(m.created_at),
    nick:     m.participant_name,
    text:     m.transcribed_text,
    y:        Math.round((m.toxicity.toxicity_score ?? 0) * 100),
    isToxic:  m.toxicity.is_toxic,
  }))
 
  const step  = Math.max(1, Math.floor(messages.length / 10))
  const xLbls = pts.map((p, i) =>
    (i === 0 || i === pts.length - 1 || i % step === 0) ? p.lbl : ''
  )
 
  const participantNames = participants.length
    ? participants.map(p => p.name)
    : [...new Set(messages.map(m => m.participant_name))]
 
  const isMultiParticipant = participantNames.length > 1
    && new Set(messages.map(m => m.participant_name)).size > 1
 
  const datasets = isMultiParticipant
    ? participantNames.map((name, i) => {
        const color = participantColors[i % participantColors.length] || '#888'
        return {
          label: name,
          data: pts.map(p => p.nick === name ? p.y : null),
          borderColor: color,
          backgroundColor: color + '20',
          borderWidth: 1.5,
          pointRadius: 4, pointHoverRadius: 8,
          pointBackgroundColor: pts.map(p =>
            p.nick === name ? (p.isToxic ? '#FF3B30' : color) : 'transparent'
          ),
          fill: false, tension: 0.15, spanGaps: true,
        }
      })
    : [{
        label: 'Probabilità tossicità (%)',
        data: pts.map(p => p.y),
        borderColor: '#FF6B6B',
        backgroundColor: '#FF6B6B20',
        borderWidth: 1.5,
        pointRadius: 5, pointHoverRadius: 8,
        pointBackgroundColor: pts.map(p => p.isToxic ? '#FF3B30' : '#34C759'),
        fill: true, tension: 0.15,
      }]
 
  return (
    <div style={{ height: 300, position: 'relative' }}>
      <Line
        data={{ labels: xLbls, datasets }}
        options={{
          responsive: true, maintainAspectRatio: false,
          animation: { duration: 150 },
          interaction: { mode: 'nearest', axis: 'x', intersect: false },
          plugins: {
            legend: {
              display: isMultiParticipant, position: 'top',
              labels: { color: '#8e8e93', font: { size: 11 }, boxWidth: 12, padding: 8 },
            },
            tooltip: {
              backgroundColor: 'rgba(28,28,30,0.95)',
              callbacks: {
                title: items => `${pts[items[0].dataIndex].lbl} · ${pts[items[0].dataIndex].nick}`,
                label: ctx => `Toxicity: ${ctx.parsed.y}% — ${pts[ctx.dataIndex].isToxic ? 'TOSSICO' : 'non tossico'}`,
                afterLabel: ctx => {
                  const t = pts[ctx.dataIndex].text
                  return t.length > 60 ? t.slice(0, 60) + '…' : t
                },
              },
            },
          },
          scales: {
            x: {
              grid: { color: 'rgba(255,255,255,0.05)' },
              ticks: { color: '#8e8e93', maxRotation: 0 },
              title: {
                display: true, text: "Minuti dall'inizio del meeting",
                color: '#636366', font: { size: 10 }
              },
            },
            y: {
              min: 0, max: 100,
              grid: { color: 'rgba(255,255,255,0.05)' },
              ticks: { color: '#8e8e93', callback: v => v + '%' },
              title: {
                display: true, text: yLabel,
                color: '#636366', font: { size: 10 }
              },
            },
          },
        }}
      />
    </div>
  )
}


// ─── ParticipantRoster ────────────────────────────────────────────────────────
function ParticipantRoster({ stats, participantColors }) {
  if (!stats?.length) return <Empty msg="Nessun dato — premi Play" />
  return (
    <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(180px, 1fr))', gap:12 }}>
      {stats.map((p,i) => {
        const color  = participantColors[i] || '#007AFF'
        const n      = p.stats.total_messages
        const d      = p.stats.sentiment.distribution
        const tc     = p.stats.toxicity.toxic_count
        const posPct = n ? Math.round(d.positive/n*100) : 0
        return (
          <div key={p.id} style={{ background:'rgba(255,255,255,0.04)', borderRadius:12, padding:14, border:`1px solid ${color}33` }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
              <div style={{ width:36, height:36, borderRadius:'50%', background:color,
                display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, color:'#fff', flexShrink:0 }}>
                {p.name.slice(0,2).toUpperCase()}
              </div>
              <div>
                <div style={{ fontSize:14, fontWeight:600, color:'#fff' }}>{p.name}</div>
                <div style={{ fontSize:11, color:'#8e8e93' }}>{n} msg · {posPct}% positivi</div>
              </div>
            </div>
            {n>0 && (
              <>
                <div style={{ display:'flex', height:5, borderRadius:3, overflow:'hidden', marginBottom:6 }}>
                  <div style={{ width:`${d.positive/n*100}%`, background:'#34C759', transition:'width 0.4s' }} />
                  <div style={{ width:`${d.neutral/n*100}%`,  background:'#FFCC00', transition:'width 0.4s' }} />
                  <div style={{ width:`${d.negative/n*100}%`, background:'#FF3B30', transition:'width 0.4s' }} />
                </div>
                <div style={{ display:'flex', gap:6, fontSize:10, color:'#8e8e93', justifyContent:'space-between' }}>
                  <span><span style={{ color:'#34C759' }}>●</span> {d.positive}</span>
                  <span><span style={{ color:'#FFCC00' }}>●</span> {d.neutral}</span>
                  <span><span style={{ color:'#FF3B30' }}>●</span> {d.negative}</span>
                  {tc>0 && <span style={{ color:'#FF3B30' }}>⚠ {tc}</span>}
                </div>
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── MessageStream ────────────────────────────────────────────────────────────
function MessageStream({ messages, limit, participantColors, participants, meetingStartTime }) {
  if (!messages?.length) return <Empty msg="Nessun messaggio" />
  const sc = l => ({ positive:'#34C759', neutral:'#FFCC00', negative:'#FF3B30' }[l]||'#8e8e93')
  const base = new Date(meetingStartTime || messages[0].created_at).getTime()
  const fmt  = ts => {
    const s = Math.max(0,(new Date(ts).getTime()-base)/1000)
    return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`
  }
  const nickColor = name => {
    const idx = participants?.findIndex(p=>p.name===name) ?? -1
    return idx>=0 ? (participantColors[idx]||'#fff') : '#fff'
  }
  return (
    <div style={{ maxHeight:380, overflowY:'auto' }}>
      {[...messages].reverse().slice(0,limit).map((m,i) => (
        <div key={i} style={{ padding:'8px 0', borderBottom:'0.5px solid rgba(255,255,255,0.06)' }}>
          <div style={{ display:'flex', gap:6, alignItems:'center', flexWrap:'wrap', marginBottom:3 }}>
            <span style={{ fontSize:11, fontWeight:700, color:nickColor(m.participant_name) }}>{m.participant_name}</span>
            <span style={{ fontSize:10, color:'#636366' }}>{fmt(m.created_at)}</span>
            <span style={{ fontSize:10, fontWeight:600, padding:'1px 6px', borderRadius:4,
              background:`${sc(m.sentiment.label)}18`, color:sc(m.sentiment.label), textTransform:'uppercase' }}>
              {m.sentiment.label.toUpperCase()} (confidence: {Math.round(m.sentiment.confidence*100)}%)
            </span>
            {m.toxicity.is_toxic && (
              <span style={{ fontSize:10, fontWeight:600, padding:'1px 6px', borderRadius:4, background:'#FF3B3018', color:'#FF3B30' }}>
                ⚠ tossico ({Math.round(m.toxicity.toxicity_score*100)}%)
              </span>
            )}
          </div>
          <div style={{ fontSize:13, color:'#ebebf5cc', lineHeight:1.5 }}>{m.transcribed_text}</div>
        </div>
      ))}
    </div>
  )
}

const Empty = ({ msg='Nessun dato' }) => (
  <div style={{ color:'#636366', fontSize:13, textAlign:'center', padding:'18px 0' }}>{msg}</div>
)

// ─── Styles ───────────────────────────────────────────────────────────────────
const S = {
  app:      { background:'#1c1c1e', fontFamily:'-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif', color:'#fff', minHeight:'100vh' },
  header:   { position:'sticky', top:0, zIndex:95, background:'rgba(28,28,30,0.97)', backdropFilter:'saturate(180%) blur(20px)', borderBottom:'0.5px solid rgba(255,255,255,0.1)' },
  hRow:     { maxWidth:1400, margin:'0 auto', display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10, padding:'12px 16px 8px' },
  hLeft:    { display:'flex', alignItems:'center', gap:10, flexWrap:'wrap', flex:1 },
  logo:     { width:32, height:32, borderRadius:'50%', background:'linear-gradient(135deg,#007AFF,#5856D6)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#fff', flexShrink:0 },
  title:    { fontSize:16, fontWeight:700, margin:0 },
  subtitle: { fontSize:11, color:'#8e8e93', margin:0 },
  select:   { background:'rgba(255,255,255,0.08)', border:'0.5px solid rgba(255,255,255,0.18)', borderRadius:8, color:'#fff', padding:'6px 10px', fontSize:12, fontWeight:600, cursor:'pointer', outline:'none' },
  btn:      { border:'none', borderRadius:8, padding:'6px 12px', fontSize:13, color:'#fff', cursor:'pointer', background:'#3a3a3c', fontWeight:600, whiteSpace:'nowrap' },
  grid:     { maxWidth:1400, margin:'0 auto', padding:'clamp(0.75rem,3vw,1.25rem)', display:'grid', gap:'clamp(0.75rem,2vw,1rem)', alignItems:'start' },
  kpiVal:   { fontSize:32, fontWeight:700, color:'#fff', lineHeight:1 },
  kpiLab:   { fontSize:11, color:'#8e8e93', marginTop:3 },
}