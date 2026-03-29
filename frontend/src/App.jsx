import { useState, useEffect, useRef, useCallback } from 'react'
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

// Simula il ritardo di elaborazione BERT per ogni messaggio (ms).
// In un sistema reale questo sarebbe il tempo che il backend impiega
// a ricevere l'audio, trascriverlo e analizzarlo con i modelli.
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
// Framerate: ogni N secondi reali viene rilasciato il prossimo
// blocco di messaggi (quelli avvenuti in quei N secondi di meeting).
// Simula il ritardo di elaborazione BERT in produzione.
const FRAMERATES = [
  { label: 'Off',  value: 0  },
  { label: '2s',   value: 2  },
  { label: '5s',   value: 5  },
  { label: '10s',  value: 10 },
  { label: '30s',  value: 30 },
]
const NAV_ITEMS = [
  { id: 'overview',     icon: '⊞', label: 'Overview' },
  { id: 'sentiment',    icon: '◎', label: 'Sentiment' },
  { id: 'toxicity',     icon: '⚠', label: 'Tossicità' },
  { id: 'participants', icon: '👥', label: 'Partecipanti' },
  { id: 'stream',       icon: '▤', label: 'Stream' },
]

const tsToSec    = ts => ts ? new Date(ts).getTime() / 1000 : 0
const secToLabel = sec => {
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60)
  return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
}
const bertDelay = () =>
  BERT_MIN_DELAY + Math.random() * (BERT_MAX_DELAY - BERT_MIN_DELAY)

// ─── Toast ────────────────────────────────────────────────────────────────────
const Toast = ({ message, type, onClose }) => {
  useEffect(() => { const t = setTimeout(onClose, 3500); return () => clearTimeout(t) }, [onClose])
  const bg = { info:'#007AFF', success:'#34C759', error:'#FF3B30', warning:'#FF9500' }[type]
  return (
    <div style={{ background:bg, color:'#fff', padding:'10px 16px', borderRadius:10,
      marginBottom:8, fontSize:13, fontWeight:600,
      boxShadow:'0 4px 12px rgba(0,0,0,0.3)', animation:'slideIn 0.3s ease' }}>
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

  // ── Playback ──────────────────────────────────────────────────────────────
  const [playbackIndex, setPlaybackIndex] = useState(0)
  const [isPlaying,     setIsPlaying]     = useState(false)

  /*
   * mode: 'live' | 'review'
   *
   * LIVE — Simula l'ingresso a un meeting in corso.
   *   • Il playback parte automaticamente.
   *   • Ogni messaggio arriva con il gap reale dai timestamp + ritardo BERT
   *     (BERT_MIN_DELAY–BERT_MAX_DELAY ms di elaborazione simulata).
   *   • joinOffset: quanti messaggi erano già avvenuti quando sei entrato.
   *     Se joinOffset > 0 quei messaggi non vengono mostrati in diretta
   *     (eri assente), ma saranno disponibili in review.
   *   • Nessun controllo velocità, nessun tasto pausa.
   *   • bertProcessing: true mentre il modello "elabora" il prossimo messaggio.
   *
   * REVIEW — Attivata a meeting concluso premendo "Rivedi dall'inizio".
   *   • Vedi tutto il transcript (inclusi i messaggi precedenti all'ingresso).
   *   • Controlli Play/Pausa, ⏮ reset, selettore velocità 1×–20×.
   *   • Export JSON/CSV disponibile.
   */
  const [mode,            setMode]           = useState('live')
  const [joinOffset,      setJoinOffset]     = useState(0)

  // Framerate simulation: l'utente sceglie quanti secondi di meeting
  // vengono "rilasciati" ogni secondo reale. Es: 10 = 10 secondi di meeting/sec.
  // Il backend viene interrogato con ?simulatedOffset=N per ricevere solo
  // i messaggi fino al secondo N del meeting. Simula il ritardo BERT reale.
  const [frameRate,        setFrameRate]      = useState(0)   // 0 = off
  const [simOffset,        setSimOffset]      = useState(0)   // secondi simulati trascorsi
  const simOffsetRef = useRef(0)
  const frameTimerRef = useRef(null)
  const [bertProcessing,  setBertProcessing] = useState(false)
  const [speed, setSpeed] = useState(5)

  const timerRef = useRef(null)
  const indexRef = useRef(0)
  const [wallSec, setWallSec] = useState(0)
  const wallRef  = useRef(0)
  const clockRef = useRef(null)

  // ── UI ────────────────────────────────────────────────────────────────────
  const [activeView,       setActiveView]      = useState('overview')
  const [meetingList,      setMeetingList]     = useState([])
  const [selectedMeeting,  setSelectedMeeting] = useState('mtg001')
  const [showWidgetPanel,  setShowWidgetPanel] = useState(false)
  const [openSettings,     setOpenSettings]    = useState(null)
  const [toasts,           setToasts]          = useState([])
  const [showJoinBanner,   setShowJoinBanner]  = useState(false)

  const DEFAULT_WIDGETS = {
    messages:true, sentimentKPI:true, toxicityKPI:true, healthScore:true,
    sentimentDist:true, timelineSentiment:true, timelineToxicity:true,
    toxicityGauge:true, participantRoster:true, messageStream:true
  }
  const [visibleWidgets, setVisibleWidgets] = useState(() => {
    try {
      const s = localStorage.getItem('visibleWidgets')
      if (s) {
        const parsed = JSON.parse(s)
        // Merge with defaults to handle new widgets added after first load
        return { ...DEFAULT_WIDGETS, ...parsed }
      }
    } catch {}
    return { ...DEFAULT_WIDGETS }
  })

  const [widgetConfigs, setWidgetConfigs] = useState({
    messages:          { participantFilter:null },
    sentimentKPI:      { participantFilter:null },
    toxicityKPI:       { participantFilter:null },
    healthScore:       { participantFilter:null },
    sentimentDist:     { participantFilter:null },
    timelineSentiment: { participantFilter:null },
    timelineToxicity:  { participantFilter:null },
    toxicityGauge:     { participantFilter:null },
    participantRoster: { participantFilter:null },
    messageStream:     { participantFilter:null, limit:30 },
  })

  const showToast = useCallback((msg, type='info') => {
    setToasts(p => [...p, { id:Date.now(), message:msg, type }])
  }, [])

  // ── playback helpers ──────────────────────────────────────────────────────
  const stopTimer = useCallback(() => {
    if (timerRef.current)  { clearTimeout(timerRef.current);  timerRef.current  = null }
  }, [])
  const stopClock = useCallback(() => {
    if (clockRef.current) { clearInterval(clockRef.current); clockRef.current = null }
  }, [])

  const stopFrameTimer = useCallback(() => {
    if (frameTimerRef.current) { clearInterval(frameTimerRef.current); frameTimerRef.current = null }
  }, [])

  const stopTimerRef = useRef(stopTimer)
  const stopClockRef = useRef(stopClock)
  useEffect(() => { stopTimerRef.current = stopTimer }, [stopTimer])
  useEffect(() => { stopClockRef.current = stopClock }, [stopClock])

  // ── data loading ──────────────────────────────────────────────────────────
  const loadMeeting = useCallback(async (meetingId, isRefresh=false) => {
    if (!isRefresh) {
      setLoading(true); setError(null)
      stopTimerRef.current(); stopClockRef.current()
      indexRef.current = 0; wallRef.current = 0
      setPlaybackIndex(0); setWallSec(0); setIsPlaying(false)
      setMode('live')
      setSimOffset(0); simOffsetRef.current = 0
    }
    try {
      const [rP, rM] = await Promise.all([
        fetch(`${API_URL}/participants`),
        fetch(`${API_URL}/meeting/${meetingId}/analysis`),
      ])
      if (!rM.ok) throw new Error(`HTTP ${rM.status}`)
      const [dP, dM] = await Promise.all([rP.json(), rM.json()])
      setParticipants(dP.participants)

      if (!isRefresh) {
        const transcript = dM.transcript
        setAllTranscript(transcript)

        /*
         * Simula l'ingresso a meeting in corso.
         * Calcoliamo quanti messaggi sarebbero già avvenuti se il meeting
         * fosse iniziato N minuti fa. Usiamo i gap reali dei timestamp:
         * scegliamo un punto di ingresso casuale tra il 20% e il 60%
         * del meeting (abbastanza da essere "in corso" ma non quasi finito).
         */
        const n = transcript.length
        if (n > 4) {
          const joinAt = Math.floor(n * (0.2 + Math.random() * 0.4))
          setJoinOffset(joinAt)
          indexRef.current = joinAt
          setPlaybackIndex(joinAt)
          // wall clock parte dal timestamp reale di ingresso
          if (transcript[joinAt]) {
            const elapsed = tsToSec(transcript[joinAt].created_at) - tsToSec(transcript[0].created_at)
            wallRef.current = elapsed
            setWallSec(elapsed)
          }
          setShowJoinBanner(true)
          setTimeout(() => setShowJoinBanner(false), 5000)
        } else {
          setJoinOffset(0)
        }
        setIsPlaying(true)
      } else {
        // refresh: solo aggiorna il transcript
        setAllTranscript(prev => {
          if (dM.transcript.length > prev.length)
            showToast(`+${dM.transcript.length - prev.length} nuovi messaggi`, 'info')
          return dM.transcript
        })
      }
    } catch {
      if (!isRefresh) { setError('Impossibile caricare il meeting'); showToast('Errore caricamento', 'error') }
    } finally {
      if (!isRefresh) setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    fetch(`${API_URL}/meetings`).then(r=>r.json()).then(d=>setMeetingList(d.meetings||[])).catch(()=>{})
  }, [])

  useEffect(() => { loadMeeting(selectedMeeting) }, [selectedMeeting, loadMeeting])

  // refresh rate rimosso: i dati mock non cambiano tra una fetch e l'altra

  useEffect(() => {
    try { localStorage.setItem('visibleWidgets', JSON.stringify(visibleWidgets)) } catch {}
  }, [visibleWidgets])

  // ── Framerate simulation (intervalli reali) ──────────────────────────────
  // Con frameRate = N secondi:
  //   ogni N secondi reali → vengono rilasciati tutti i messaggi del meeting
  //   avvenuti nei successivi N secondi di tempo del meeting.
  // Simula il comportamento reale: BERT elabora un blocco, poi lo rilascia.
  // Con frameRate = 0 → off, usa scheduleNext con gap naturali.
  useEffect(() => {
    stopFrameTimer()
    if (frameRate === 0 || mode !== 'live' || !allTranscript.length) return

    // Ferma il playback continuo di scheduleNext (non serve in frame-mode)
    stopTimer()
    stopClock()

    const baseTs = tsToSec(allTranscript[0].created_at)

    // Partenza: se simOffsetRef è ancora a 0 (primo avvio), usa joinOffset.
    // Se cambio frameRate a meeting in corso, riprendo esattamente da dove ero.
    if (simOffsetRef.current === 0) {
      const startTs = joinOffset > 0 && allTranscript[joinOffset]
        ? tsToSec(allTranscript[joinOffset].created_at) - baseTs
        : 0
      simOffsetRef.current = startTs
    }

    frameTimerRef.current = setInterval(() => {
      simOffsetRef.current += frameRate
      const meetingCursor = simOffsetRef.current

      // Trova l'indice del primo messaggio oltre la finestra corrente
      let nextIdx = allTranscript.findIndex(
        m => tsToSec(m.created_at) - baseTs > meetingCursor
      )
      if (nextIdx === -1) nextIdx = allTranscript.length

      indexRef.current = nextIdx
      setPlaybackIndex(nextIdx)

      // Aggiorna il wallClock all'ultimo messaggio rilasciato
      const lastMsg = allTranscript[nextIdx - 1]
      if (lastMsg) {
        const ws = tsToSec(lastMsg.created_at) - baseTs
        wallRef.current = ws
        setWallSec(ws)
      }

      // Meeting concluso — snap timer al valore esatto
      if (nextIdx >= allTranscript.length) {
        stopFrameTimer()
        stopClock()
        setIsPlaying(false)
        simOffsetRef.current = 0  // reset per prossimo meeting
        const exact = tsToSec(allTranscript[allTranscript.length - 1].created_at) - baseTs
        wallRef.current = exact
        setWallSec(exact)
      }
    }, frameRate * 1000)

    // Avvia subito con il primo batch (messaggi precedenti al join già visibili)
    setIsPlaying(true)

    return () => stopFrameTimer()
  }, [frameRate, mode, allTranscript, joinOffset, stopFrameTimer, stopTimer, stopClock])

  // ── playback engine ───────────────────────────────────────────────────────
  const scheduleNext = useCallback((idx, transcript, spd, isLive) => {
    if (idx >= transcript.length) {
      setIsPlaying(false)
      setBertProcessing(false)
      // Snappa il wallClock all'ultimo timestamp esatto (evita scarto finale)
      if (transcript.length > 0) {
        const exact = tsToSec(transcript[transcript.length - 1].created_at)
                    - tsToSec(transcript[0].created_at)
        wallRef.current = exact
        setWallSec(exact)
      }
      stopTimerRef.current()
      stopClockRef.current()
      return
    }

    // Gap naturale tra messaggi (dai timestamp reali)
    const gap = transcript[idx + 1]
      ? tsToSec(transcript[idx + 1].created_at) - tsToSec(transcript[idx].created_at)
      : 1

    const naturalDelay = Math.max(80, (gap * 1000) / spd)

    // In live mode aggiungiamo il ritardo di elaborazione BERT
    const delay = isLive ? naturalDelay + bertDelay() : naturalDelay

    // Mostra l'indicatore "BERT sta elaborando" nell'ultimo tratto
    if (isLive && delay > 400) {
      setTimeout(() => setBertProcessing(true), Math.max(0, delay - bertDelay()))
    }

    timerRef.current = setTimeout(() => {
      setBertProcessing(false)
      const next = idx + 1
      indexRef.current = next
      setPlaybackIndex(next)
      if (transcript[next-1])
        wallRef.current = tsToSec(transcript[next-1].created_at) - tsToSec(transcript[0].created_at)
      scheduleNext(next, transcript, spd, isLive)
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
        // In review: resetta dall'inizio assoluto
        indexRef.current = mode === 'review' ? 0 : joinOffset
        wallRef.current  = mode === 'review' ? 0 : (
          allTranscript[joinOffset] ? tsToSec(allTranscript[joinOffset].created_at) - tsToSec(allTranscript[0].created_at) : 0
        )
        setPlaybackIndex(indexRef.current)
        setWallSec(wallRef.current)
      }
      const isLive = mode === 'live'
      // In live mode il framerate a intervalli è gestito dall'useEffect separato.
      // scheduleNext in live usa sempre velocità 1× (gap reali + ritardo BERT).
      const effectiveSpeed = isLive ? 1 : speed
      scheduleNext(indexRef.current, allTranscript, effectiveSpeed, isLive)
      startClock(effectiveSpeed)
    } else {
      stopTimer(); stopClock(); setBertProcessing(false)
    }
    return () => { stopTimer(); stopClock(); setBertProcessing(false) }
  }, [isPlaying, allTranscript, speed, mode, joinOffset, scheduleNext, startClock, stopTimer, stopClock])

  // ── handlers ─────────────────────────────────────────────────────────────
  // Pausa/play solo in review
  const handlePlayPause = () => { if (mode === 'review') setIsPlaying(p => !p) }

  // Entra in review: resetta al messaggio 0, dà controllo all'utente
  const enterReviewMode = () => {
    stopTimer(); stopClock(); setIsPlaying(false)
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

  // ── export (solo a meeting finito) ────────────────────────────────────────
  const exportJSON = () => {
    const data = { meeting_id:selectedMeeting, transcript:allTranscript, stats:calcStats(allTranscript) }
    const blob  = new Blob([JSON.stringify(data, null, 2)], { type:'application/json' })
    const a     = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download:`${selectedMeeting}_${new Date().toISOString().split('T')[0]}.json`
    })
    a.click(); URL.revokeObjectURL(a.href)
    showToast('JSON esportato', 'success')
  }

  const exportCSV = () => {
    const rows = allTranscript.map(m =>
      `${m.conversation_turn},"${m.participant_name}","${m.transcribed_text.replace(/"/g,'""')}",${m.sentiment.label},${Math.round(m.sentiment.score*100)}%,${m.toxicity.is_toxic},${m.toxicity.severity},${m.created_at}`
    )
    const blob = new Blob(
      [['Turno,Partecipante,Testo,Sentiment,Score,Tossico,Severità,Timestamp', ...rows].join('\n')],
      { type:'text/csv;charset=utf-8;' }
    )
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(blob),
      download:`${selectedMeeting}_${new Date().toISOString().split('T')[0]}.csv`
    })
    a.click(); URL.revokeObjectURL(a.href)
    showToast('CSV esportato', 'success')
  }

  // ── computed ──────────────────────────────────────────────────────────────
  /*
   * liveTranscript: messaggi che l'utente vede nei widget.
   * - In LIVE: solo i messaggi da joinOffset in poi (quelli durante la tua presenza)
   * - In REVIEW: tutto, dall'inizio assoluto
   */
  // Mostra sempre tutto il transcript fino al punto corrente del playback.
  // In live mode il joinOffset determina DA DOVE iniziano ad arrivare nuovi messaggi,
  // ma i messaggi precedenti all'ingresso vengono mostrati subito nei widget
  // (situazione pregressa del meeting).
  const liveTranscript = allTranscript.slice(0, playbackIndex)

  const total      = allTranscript.length
  const baseTs     = total > 0 ? tsToSec(allTranscript[0].created_at) : 0
  const totalSec   = total > 0 ? tsToSec(allTranscript[total-1].created_at) - baseTs : 0

  // Progress bar: in live parte dal punto di ingresso
  const liveStartTs = joinOffset > 0 && allTranscript[joinOffset]
    ? tsToSec(allTranscript[joinOffset].created_at) - baseTs
    : 0
  const liveTotalSec = totalSec - liveStartTs
  const progressPct  = mode === 'review'
    ? (totalSec > 0 ? Math.min((wallSec / totalSec) * 100, 100) : 0)
    : (liveTotalSec > 0 ? Math.min(((wallSec - liveStartTs) / liveTotalSec) * 100, 0) + (
        (wallSec - liveStartTs) / liveTotalSec * 100
      ) : 0)

  const isFinished = playbackIndex >= total && total > 0
  const liveEnded  = isFinished && mode === 'live'

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

  const toggleWidget       = id => setVisibleWidgets(p => ({ ...p, [id]: !(p[id] !== false) }))
  const updateWidgetConfig = (id,u) => setWidgetConfigs(p => ({ ...p, [id]:{ ...p[id], ...u } }))

  const getFiltered = id => {
    const pf = widgetConfigs[id]?.participantFilter
    if (!pf) return liveTranscript
    const p = participants.find(x => x.id === pf)
    return p ? liveTranscript.filter(e => e.participant_name === p.name) : liveTranscript
  }
  const F    = id  => getFiltered(id)
  const S_id = id  => calcStats(F(id))

  const getParticipantStats = () =>
    participants.map(p => ({
      ...p, stats: calcStats(liveTranscript.filter(e => e.participant_name === p.name))
    }))

  // Sentiment Polarity Index: metrica standard in letteratura sentiment analysis.
  // Range [-1, +1]: -1 = tutto negativo, 0 = bilanciato, +1 = tutto positivo.
  // Formula: (positivi - negativi) / totale
  const calcPolarity = stats => {
    if (stats.total_messages === 0) return null
    const { positive, negative } = stats.sentiment.distribution
    return ((positive - negative) / stats.total_messages)
  }

  // ── widget sections ───────────────────────────────────────────────────────
  const SECTIONS = [
    { title:'KPI', items:[
      { id:'messages',    name:'Messaggi',      desc:'Contatore messaggi ricevuti.' },
      { id:'sentimentKPI',name:'Sentiment %',   desc:'Distribuzione positivo/neutro/negativo.' },
      { id:'toxicityKPI', name:'Tossicità',     desc:'Conteggio e % messaggi tossici.' },
      { id:'healthScore', name:'Sentiment Polarity', desc:'Indice [-1,+1]: (positivi-negativi)/totale. 0=bilanciato.' },
    ]},
    { title:'Grafici', items:[
      { id:'sentimentDist',     name:'Distribuzione Sentiment', desc:'Barra pos/neu/neg in percentuale.' },
      { id:'timelineSentiment', name:'Timeline Sentiment',      desc:'Score per ogni messaggio nel tempo.' },
      { id:'timelineToxicity',  name:'Timeline Tossicità',      desc:'Score tossicità per ogni messaggio.' },
      { id:'toxicityGauge',     name:'Gauge Tossicità',         desc:'Media tossicità su gauge.' },
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

  const buildWidgets = () => {
    const polarity = calcPolarity(S_id('healthScore'))
    const wMessages   = wgt('messages','Messaggi',false,
      <><div style={S.kpiVal}>{F('messages').length}</div><div style={S.kpiLab}>messaggi ricevuti</div></>)
    const wSentKPI    = wgt('sentimentKPI','Sentiment',false,   <SentimentKPI stats={S_id('sentimentKPI')} />)
    const wToxKPI     = wgt('toxicityKPI', 'Tossicità', false,  <ToxicityKPI  stats={S_id('toxicityKPI')} />)
    const wHealth     = wgt('healthScore','Sentiment Polarity Index',false,(() => {
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
    const wSentDist   = wgt('sentimentDist','Distribuzione Sentiment',true,  <SentimentDistChart stats={S_id('sentimentDist')} />)
    const wTimeSent   = wgt('timelineSentiment','Timeline Sentiment — ogni punto = un messaggio',true,
      <TimelineChart messages={F('timelineSentiment')} metric="sentiment" color="#00C7BE" yLabel="Sentiment score (0–100%)" />)
    const wTimeTox    = wgt('timelineToxicity','Timeline Tossicità — ogni punto = un messaggio',true,
      <TimelineChart messages={F('timelineToxicity')} metric="toxicity"  color="#FF6B6B" yLabel="Toxicity score (0–100%)" />)
    const wGauge      = wgt('toxicityGauge','Messaggi Tossici (%)',!isMobile,
      <ToxicityGauge score={S_id('toxicityGauge').toxicity.toxic_ratio} />)
    const wRoster     = wgt('participantRoster','Partecipanti',true,
      <ParticipantRoster stats={getParticipantStats()} participantColors={PARTICIPANT_COLORS} />)
    const wStream     = wgt('messageStream','Stream Messaggi',true,
      <MessageStream messages={F('messageStream')} limit={widgetConfigs.messageStream?.limit||30}
        participantColors={PARTICIPANT_COLORS} participants={participants} />)

    const views = {
      overview:     [wMessages, wHealth, wSentKPI, wToxKPI, wSentDist, wTimeSent, wTimeTox, wStream, wRoster],
      sentiment:    [wSentKPI, wSentDist, wTimeSent],
      toxicity:     [wToxKPI, wTimeTox, wGauge],
      participants: [wRoster],
      stream:       [wMessages, wStream],
    }
    return (views[activeView] || views.overview).filter(Boolean)
  }

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div style={S.app}>
      {/* Toasts */}
      <div style={{ position:'fixed', top:80, right:16, zIndex:999, pointerEvents:'none' }}>
        {toasts.map(t => (
          <Toast key={t.id} message={t.message} type={t.type}
            onClose={() => setToasts(p => p.filter(x => x.id !== t.id))} />
        ))}
      </div>

      <div style={{ display:'flex', minHeight:'100vh' }}>

        {/* ── Sidebar desktop ───────────────────────────────────────────── */}
        {!isMobile && (
          <nav style={S.sidebar}>
            <div style={S.sbLogo}>MI</div>
            <div style={{ height:'0.5px', background:'rgba(255,255,255,0.07)', margin:'0 10px 8px' }} />
            {NAV_ITEMS.map(item => {
              const active = activeView === item.id
              return (
                <button key={item.id} onClick={() => setActiveView(item.id)}
                  style={{ ...S.sbItem,
                    background: active ? 'rgba(0,122,255,0.15)' : 'transparent',
                    borderLeft: active ? '2px solid #007AFF' : '2px solid transparent',
                    color: active ? '#fff' : '#8e8e93' }}>
                  <span style={{ fontSize:17, color: active ? '#007AFF' : '#636366' }}>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              )
            })}
            <div style={{ flex:1 }} />
            <div style={{ fontSize:10, color:'#3a3a3c', padding:'12px 14px', lineHeight:1.4, fontWeight:600, textTransform:'uppercase', letterSpacing:'0.5px' }}>
              Meeting<br/>Intelligence
            </div>
          </nav>
        )}

        {/* ── Main content ──────────────────────────────────────────────── */}
        <div style={{ flex:1, minWidth:0, paddingBottom: isMobile ? 72 : 0 }}>

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

                {/* ── LIVE ────────────────────────────────────────────── */}
                {mode === 'live' && !liveEnded && (
                  <>
                    <div style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
                      background:'rgba(255,59,48,0.15)', border:'0.5px solid rgba(255,59,48,0.4)',
                      borderRadius:8 }}>
                      <span style={{ width:8, height:8, borderRadius:'50%', background:'#FF3B30',
                        animation:'pulse 1.5s ease-in-out infinite', flexShrink:0 }} />
                      <span style={{ fontSize:13, fontWeight:700, color:'#FF3B30' }}>IN DIRETTA</span>
                    </div>

                    <span style={{ fontSize:13, fontWeight:700, fontVariantNumeric:'tabular-nums', color:'#fff' }}>
                      {secToLabel(Math.min(wallSec, totalSec))} / {secToLabel(totalSec)}
                    </span>

                    {/* Selettore framerate: 0=real-time, N=N× accelerato */}
                    <select value={frameRate}
                      onChange={e => setFrameRate(Number(e.target.value))}
                      style={S.select}
                      title="Velocità di avanzamento del meeting (0=tempo reale)">
                      {FRAMERATES.map(o => <option key={o.value} value={o.value}>⚡ {o.label}</option>)}
                    </select>

                  </>
                )}

                {/* Badge CONCLUSO — sostituisce IN DIRETTA a fine live */}
                {liveEnded && (
                  <div style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
                    background:'rgba(52,199,89,0.15)', border:'0.5px solid rgba(52,199,89,0.4)',
                    borderRadius:8 }}>
                    <span style={{ fontSize:13, fontWeight:700, color:'#34C759' }}>✓ CONCLUSO</span>
                  </div>
                )}

                {/* ── REVIEW ──────────────────────────────────────────── */}
                {mode === 'review' && (
                  <>
                    <button onClick={handleReset} style={S.btn} title="Torna all'inizio">⏮</button>
                    <button onClick={handlePlayPause}
                      style={{ ...S.btn, background: isPlaying ? '#FF9500' : '#007AFF', minWidth:86 }}>
                      {isPlaying ? '⏸ Pausa' : isFinished ? '↺ Riparti' : '▶ Play'}
                    </button>

                    {/* Selettore velocità — solo in review */}
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
                {/* Indicatore elaborazione BERT */}
                {bertProcessing && mode === 'live' && (
                  <span style={{ fontSize:10, color:'#FF9500', display:'flex', alignItems:'center', gap:4 }}>
                    <span style={{ animation:'spin 1s linear infinite', display:'inline-block' }}>⏳</span>
                    BERT sta elaborando…
                  </span>
                )}
                <span style={{ color: isPlaying ? '#007AFF' : isFinished ? '#34C759' : '#636366' }}>
                  {mode==='live'  && isPlaying   && '● In diretta'}
                  {mode==='live'  && liveEnded   && '✓ Meeting concluso'}
                  {mode==='review'&& isPlaying   && `▶ Revisione ${speed}×`}
                  {mode==='review'&& !isPlaying  && !isFinished && '⏸ In pausa'}
                  {mode==='review'&& isFinished  && '✓ Fine revisione'}
                </span>
              </div>
            </div>

            {/* Meeting concluso in live → offri revisione + export */}
            {liveEnded && (
              <div style={{ maxWidth:1400, margin:'0 auto', padding:'8px 16px 12px',
                display:'flex', gap:10, alignItems:'center', flexWrap:'wrap',
                borderTop:'0.5px solid rgba(255,255,255,0.08)' }}>
                <span style={{ fontSize:13, fontWeight:600, color:'#fff' }}>Meeting concluso.</span>
                <button onClick={enterReviewMode} style={{ ...S.btn, background:'#007AFF' }}>
                  ↩ Rivedi dall'inizio
                </button>
                <button onClick={exportJSON} style={{ ...S.btn, background:'#5856D6' }}>📥 JSON</button>
                <button onClick={exportCSV}  style={{ ...S.btn, background:'#5856D6' }}>📊 CSV</button>
              </div>
            )}
            {/* In revisione finita → solo export */}
            {mode==='review' && isFinished && (
              <div style={{ maxWidth:1400, margin:'0 auto', padding:'8px 16px 12px', display:'flex', gap:8, alignItems:'center' }}>
                <span style={{ fontSize:12, color:'#8e8e93' }}>Scarica i dati:</span>
                <button onClick={exportJSON} style={{ ...S.btn, background:'#5856D6' }}>📥 JSON</button>
                <button onClick={exportCSV}  style={{ ...S.btn, background:'#5856D6' }}>📊 CSV</button>
              </div>
            )}
          </div>

          {/* Banner ingresso a meeting in corso — si mostra 5s poi scompare */}
          {showJoinBanner && joinOffset > 0 && (
            <div style={{ margin:'12px 16px', padding:'10px 14px',
              background:'rgba(0,122,255,0.1)', border:'0.5px solid rgba(0,122,255,0.3)',
              borderRadius:10, fontSize:13, color:'#007AFF',
              display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              <span>
                ℹ️ Sei entrato con il meeting in corso al messaggio <strong>{joinOffset+1}/{total}</strong>.
                I messaggi precedenti sono già visibili nei widget.
              </span>
              <button onClick={() => setShowJoinBanner(false)}
                style={{ background:'none', border:'none', color:'#007AFF', cursor:'pointer', fontSize:16, padding:'0 4px' }}>✕</button>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ margin:16, padding:'12px 16px', background:'rgba(255,59,48,0.15)',
              border:'0.5px solid rgba(255,59,48,0.3)', borderRadius:10, color:'#FF3B30', fontSize:14 }}>
              ⚠ {error}
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', height:'60vh', gap:16 }}>
              <div style={{ width:32, height:32, border:'3px solid rgba(255,255,255,0.1)', borderTop:'3px solid #007AFF', borderRadius:'50%', animation:'spin 1s linear infinite' }} />
              <p style={{ color:'#8e8e93', fontSize:14 }}>Connessione al meeting…</p>
            </div>
          )}

          {/* Review empty state (reset premuto) */}
          {!loading && mode==='review' && playbackIndex===0 && !isPlaying && (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', minHeight:'60vh', gap:16, padding:24 }}>
              <div style={{ fontSize:48, color:'#3a3a3c' }}>↩</div>
              <div style={{ fontSize:20, fontWeight:700 }}>Revisione</div>
              <div style={{ fontSize:14, color:'#8e8e93', textAlign:'center', lineHeight:1.7 }}>
                {total} messaggi totali · {secToLabel(totalSec)} durata<br/>
                Premi <strong>Play</strong> e scegli la velocità
              </div>
              <button onClick={handlePlayPause}
                style={{ ...S.btn, background:'#007AFF', padding:'14px 36px', fontSize:16, fontWeight:700, borderRadius:14 }}>
                ▶ Inizia Revisione
              </button>
            </div>
          )}

          {/* Widget grid */}
          {!loading && liveTranscript.length > 0 && (
            <div style={{ ...S.grid, gridTemplateColumns: isSmall ? '1fr' : isMobile ? 'repeat(2, minmax(140px, 1fr))' : 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {activeView !== 'overview' && (
                <div style={{ gridColumn:'1/-1', fontSize:18, fontWeight:700, color:'#fff', padding:'4px 0 8px', display:'flex', alignItems:'center', gap:8 }}>
                  {NAV_ITEMS.find(n => n.id===activeView)?.icon}{' '}
                  {NAV_ITEMS.find(n => n.id===activeView)?.label}
                </div>
              )}
              {buildWidgets()}
            </div>
          )}
        </div>
      </div>

      {/* ── Bottom Nav mobile ─────────────────────────────────────────────── */}
      {isMobile && (
        <nav style={S.bottomNav}>
          {NAV_ITEMS.map(item => {
            const active = activeView === item.id
            return (
              <button key={item.id} onClick={() => setActiveView(item.id)}
                style={{ ...S.bottomNavItem, color: active ? '#007AFF' : '#8e8e93', fontWeight: active ? 700 : 400 }}>
                <span style={{ fontSize:22 }}>{item.icon}</span>
                <span style={{ fontSize:10 }}>{item.label}</span>
              </button>
            )
          })}
        </nav>
      )}

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
                            color:      visibleWidgets[w.id]!==false ? '#fff'     : '#8e8e93' }}
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
  const avgPct = Math.round((stats.sentiment.average_score||0)*100)
  return (
    <div>
      <div style={{ fontSize:36, fontWeight:700, color:'#34C759', lineHeight:1 }}>{posPct}%</div>
      <div style={{ fontSize:12, color:'#8e8e93', marginBottom:12 }}>messaggi positivi</div>
      <div style={{ display:'flex', height:8, borderRadius:4, overflow:'hidden', marginBottom:8 }}>
        <div style={{ width:`${posPct}%`, background:'#34C759', transition:'width 0.4s' }} />
        <div style={{ width:`${neuPct}%`, background:'#FFCC00', transition:'width 0.4s' }} />
        <div style={{ width:`${negPct}%`, background:'#FF3B30', transition:'width 0.4s' }} />
      </div>
      <div style={{ display:'flex', gap:10, fontSize:11, flexWrap:'wrap', marginBottom:10 }}>
        <span style={{ color:'#34C759' }}>● Positivi: {positive} ({posPct}%)</span>
        <span style={{ color:'#FFCC00' }}>● Neutri: {neutral} ({neuPct}%)</span>
        <span style={{ color:'#FF3B30' }}>● Negativi: {negative} ({negPct}%)</span>
      </div>
      <div style={{ fontSize:12, color:'#8e8e93' }}>
        Score medio: <strong style={{ color:'#fff' }}>{avgPct}%</strong>
        <span style={{ fontSize:10, color:'#636366', marginLeft:4 }}>(0% = molto neg., 100% = molto pos.)</span>
      </div>
    </div>
  )
}

// ─── ToxicityKPI ──────────────────────────────────────────────────────────────
function ToxicityKPI({ stats }) {
  const n = stats.total_messages
  if (n===0) return <Empty />
  const { toxic_count, toxic_ratio, severity_distribution:sv, average_toxicity_score:avg } = stats.toxicity
  const pct    = Math.round(toxic_ratio*100)
  const avgPct = Math.round((avg||0)*100)
  const color  = pct>20 ? '#FF3B30' : pct>5 ? '#FF9500' : '#34C759'
  return (
    <div>
      <div style={{ fontSize:36, fontWeight:700, color, lineHeight:1 }}>{toxic_count}</div>
      <div style={{ fontSize:12, color:'#8e8e93', marginBottom:12 }}>messaggi tossici su {n} ({pct}%)</div>
      {/* Distribuzione severità: tutti i messaggi categorizzati per score BERT grezzo,
           indipendentemente dalla soglia 0.5. Bassi = score<0.4, Medi = 0.4–0.7, Alti = >0.7 */}
      <div style={{ fontSize:10, color:'#636366', marginBottom:4 }}>
        Distribuzione score grezzo (tutti i messaggi):
      </div>
      <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:10 }}>
        {[['Score basso',sv.low,'#34C759'],['Score medio',sv.medium,'#FF9500'],['Score alto',sv.high,'#FF3B30']].map(([lbl,val,c]) => (
          <span key={lbl} style={{ fontSize:11, fontWeight:600, padding:'2px 8px', borderRadius:5, background:`${c}18`, color:c }}>
            {val} {lbl}
          </span>
        ))}
      </div>
      <div style={{ fontSize:11, color:'#636366' }}>
        Soglia tossico: score &gt; 50% · score medio = {avgPct}%
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
function TimelineChart({ messages, metric, color, yLabel }) {
  if (!messages?.length) return <Empty />
  const base = new Date(messages[0].created_at).getTime()
  const fmt  = ts => {
    const s = Math.max(0,(new Date(ts).getTime()-base)/1000)
    return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`
  }
  const pts = messages.map(m => ({
    y: Math.round((metric==='sentiment' ? m.sentiment.score : m.toxicity.toxicity_score)*100),
    lbl:fmt(m.created_at), nick:m.participant_name, text:m.transcribed_text,
    label: metric==='sentiment' ? m.sentiment.label : m.toxicity.severity
  }))
  const step  = Math.max(1,Math.floor(messages.length/8))
  const xLbls = pts.map((p,i) => (i===0||i===pts.length-1||i%step===0) ? p.lbl : '')
  const ptColors = pts.map(p =>
    metric==='sentiment'
      ? (p.label==='positive'?'#34C759':p.label==='negative'?'#FF3B30':'#FFCC00')
      : (p.label==='high'?'#FF3B30':p.label==='medium'?'#FF9500':'#34C759')
  )
  return (
    <div style={{ height:280 }}>
      <Line
        data={{ labels:xLbls, datasets:[{
          label: metric==='sentiment' ? 'Sentiment score (%)' : 'Toxicity score (%)',
          data: pts.map(p=>p.y), borderColor:color, backgroundColor:color+'20', borderWidth:1.5,
          pointRadius:4, pointHoverRadius:7, pointBackgroundColor:ptColors,
          fill:true, tension:0.1
        }]}}
        options={{ responsive:true, maintainAspectRatio:false, animation:{ duration:150 },
          plugins:{ legend:{ display:false },
            tooltip:{ backgroundColor:'rgba(28,28,30,0.95)', callbacks:{
              title: items=>`${pts[items[0].dataIndex].lbl} · ${pts[items[0].dataIndex].nick}`,
              label: ctx  =>`${ctx.parsed.y}% — ${pts[ctx.dataIndex].label}`,
              afterLabel: ctx=>{ const t=pts[ctx.dataIndex].text; return t.length>60?t.slice(0,60)+'…':t }
            }}},
          scales:{
            x:{ grid:{ color:'rgba(255,255,255,0.05)' }, ticks:{ color:'#8e8e93', maxRotation:0 },
              title:{ display:true, text:'Minuti dall\'inizio del meeting', color:'#636366', font:{ size:10 } } },
            y:{ min:0, max:100, grid:{ color:'rgba(255,255,255,0.05)' },
              ticks:{ color:'#8e8e93', callback:v=>v+'%' },
              title:{ display:true, text:yLabel, color:'#636366', font:{ size:10 } } }
          } }}
      />
    </div>
  )
}

// ─── ToxicityGauge ────────────────────────────────────────────────────────────
function ToxicityGauge({ score }) {
  const p   = Math.min(Math.max(score||0,0),1)
  const pct = Math.round(p*100)
  const col = p<0.33?'#34C759':p<0.66?'#FF9500':'#FF3B30'
  const lbl = p<0.33?'Bassa':p<0.66?'Media':'Alta'
  return (
    <div style={{ height:140, position:'relative', display:'flex', alignItems:'center', justifyContent:'center' }}>
      <Doughnut
        data={{ datasets:[{ data:[p,1-p], backgroundColor:[col,'rgba(255,255,255,0.07)'], borderWidth:0, circumference:180, rotation:270 }]}}
        options={{ responsive:true, maintainAspectRatio:false, cutout:'75%', animation:{ duration:300 },
          plugins:{ legend:{ display:false }, tooltip:{ enabled:false } } }}
      />
      <div style={{ position:'absolute', bottom:8, textAlign:'center' }}>
        <div style={{ fontSize:22, fontWeight:700, color:col }}>{pct}%</div>
        <div style={{ fontSize:11, color:'#8e8e93' }}>Tossicità {lbl}</div>
        <div style={{ fontSize:10, color:'#636366' }}>% messaggi sopra soglia 0.5</div>
      </div>
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
function MessageStream({ messages, limit, participantColors, participants }) {
  if (!messages?.length) return <Empty msg="Nessun messaggio" />
  const sc = l => ({ positive:'#34C759', neutral:'#FFCC00', negative:'#FF3B30' }[l]||'#8e8e93')
  const base = new Date(messages[0].created_at).getTime()
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
              {m.sentiment.label} · {Math.round(m.sentiment.score*100)}%
            </span>
            {m.toxicity.is_toxic && (
              <span style={{ fontSize:10, fontWeight:600, padding:'1px 6px', borderRadius:4, background:'#FF3B3018', color:'#FF3B30' }}>
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

const Empty = ({ msg='Nessun dato' }) => (
  <div style={{ color:'#636366', fontSize:13, textAlign:'center', padding:'18px 0' }}>{msg}</div>
)

// ─── Styles ───────────────────────────────────────────────────────────────────
const S = {
  app:     { background:'#1c1c1e', fontFamily:'-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif', color:'#fff', minHeight:'100vh' },
  sidebar: { width:190, position:'sticky', top:0, height:'100vh', flexShrink:0, background:'rgba(20,20,22,0.98)', borderRight:'0.5px solid rgba(255,255,255,0.08)', display:'flex', flexDirection:'column', padding:'16px 0', overflow:'hidden' },
  sbLogo:  { width:34, height:34, borderRadius:'50%', background:'linear-gradient(135deg,#007AFF,#5856D6)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#fff', margin:'0 auto 12px' },
  sbItem:  { background:'none', border:'none', borderLeft:'2px solid transparent', cursor:'pointer', display:'flex', alignItems:'center', gap:10, padding:'10px 14px', fontSize:13, fontWeight:500, width:'100%', whiteSpace:'nowrap', transition:'background 0.15s' },
  header:  { position:'sticky', top:0, zIndex:95, background:'rgba(28,28,30,0.97)', backdropFilter:'saturate(180%) blur(20px)', borderBottom:'0.5px solid rgba(255,255,255,0.1)' },
  hRow:    { maxWidth:1400, margin:'0 auto', display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:10, padding:'12px 16px 8px' },
  hLeft:   { display:'flex', alignItems:'center', gap:10, flexWrap:'wrap', flex:1 },
  logo:    { width:32, height:32, borderRadius:'50%', background:'linear-gradient(135deg,#007AFF,#5856D6)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'#fff', flexShrink:0 },
  title:   { fontSize:16, fontWeight:700, margin:0 },
  subtitle:{ fontSize:11, color:'#8e8e93', margin:0 },
  select:  { background:'rgba(255,255,255,0.08)', border:'0.5px solid rgba(255,255,255,0.18)', borderRadius:8, color:'#fff', padding:'6px 10px', fontSize:12, fontWeight:600, cursor:'pointer', outline:'none' },
  btn:     { border:'none', borderRadius:8, padding:'6px 12px', fontSize:13, color:'#fff', cursor:'pointer', background:'#3a3a3c', fontWeight:600, whiteSpace:'nowrap' },
  grid:    { maxWidth:1400, margin:'0 auto', padding:'clamp(0.75rem,3vw,1.25rem)', display:'grid', gap:'clamp(0.75rem,2vw,1rem)', alignItems:'start' },
  kpiVal:  { fontSize:32, fontWeight:700, color:'#fff', lineHeight:1 },
  kpiLab:  { fontSize:11, color:'#8e8e93', marginTop:3 },
  bottomNav:    { position:'fixed', bottom:0, left:0, right:0, zIndex:100, background:'rgba(20,20,22,0.98)', borderTop:'0.5px solid rgba(255,255,255,0.1)', display:'flex', paddingBottom:'env(safe-area-inset-bottom,0px)' },
  bottomNavItem:{ flex:1, background:'none', border:'none', cursor:'pointer', display:'flex', flexDirection:'column', alignItems:'center', gap:2, padding:'8px 4px 6px' },
}