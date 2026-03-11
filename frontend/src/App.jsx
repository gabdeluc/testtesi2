import { useState, useEffect, useRef } from 'react'
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
)

const API_URL = 'http://localhost:8000'
const POLL_INTERVAL_MS = 15000 // 15 secondi

function App() {
  const [meetingData, setMeetingData] = useState(null)
  const [participants, setParticipants] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [isPolling, setIsPolling] = useState(true)
  const [pollingCountdown, setPollingCountdown] = useState(POLL_INTERVAL_MS / 1000)
  const pollingRef = useRef(null)
  const countdownRef = useRef(null)

  const [widgetConfigs, setWidgetConfigs] = useState({
    messages:         { participantFilter: null, color: '#FF3B30', showDetails: true },
    sentiment:        { participantFilter: null, color: '#34C759', showDetails: true },
    toxicity:         { participantFilter: null, color: '#FF9500', showDetails: true },
    sentimentDist:    { participantFilter: null, color: '#007AFF', showLabels: true, animated: true },
    toxicityGauge:    { participantFilter: null, color: '#5856D6', showDetails: true },
    timelineSentiment:{ participantFilter: null, color: '#00C7BE', showGrid: true, showArea: true, metric: 'sentiment' },
    timelineToxicity: { participantFilter: null, color: '#FF6B6B', showGrid: true, showArea: true, metric: 'toxicity' },
    messageStream:    { participantFilter: null, color: '#FF2D55', limit: 30, showTimestamps: true },
    participantRoster:{ participantFilter: null, color: '#BF5AF2', showDetails: true }
  })

  const [visibleWidgets, setVisibleWidgets] = useState(() => {
    const saved = localStorage.getItem('visibleWidgets')
    return saved ? JSON.parse(saved) : {
      messages: true, sentiment: true, toxicity: true, sentimentDist: true,
      toxicityGauge: true, timelineSentiment: true, timelineToxicity: true,
      messageStream: true, participantRoster: true
    }
  })

  const [openSettings, setOpenSettings] = useState(null)
  const [showWidgetPanel, setShowWidgetPanel] = useState(false)

  // ─── Data fetching ────────────────────────────────────────────────
  const loadInitialData = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const respPart = await fetch(`${API_URL}/participants`)
      const dataPart = await respPart.json()
      setParticipants(dataPart.participants)

      const response = await fetch(`${API_URL}/meeting/mtg001/analysis`)
      if (!response.ok) throw new Error(`Status ${response.status}`)
      const data = await response.json()
      setMeetingData(data)
      setLastUpdated(new Date())
      setError(null)
    } catch (err) {
      setError('Unable to load meeting data')
    } finally {
      if (!silent) setLoading(false)
    }
  }

  // ─── Polling setup ────────────────────────────────────────────────
  const startPolling = () => {
    stopPolling()
    setPollingCountdown(POLL_INTERVAL_MS / 1000)

    // Countdown visivo
    countdownRef.current = setInterval(() => {
      setPollingCountdown(prev => {
        if (prev <= 1) return POLL_INTERVAL_MS / 1000
        return prev - 1
      })
    }, 1000)

    // Fetch reale
    pollingRef.current = setInterval(() => {
      loadInitialData(true) // silent = no spinner
      setPollingCountdown(POLL_INTERVAL_MS / 1000)
    }, POLL_INTERVAL_MS)
  }

  const stopPolling = () => {
    if (pollingRef.current)   clearInterval(pollingRef.current)
    if (countdownRef.current) clearInterval(countdownRef.current)
  }

  useEffect(() => {
    loadInitialData()
    return () => stopPolling()
  }, [])

  useEffect(() => {
    if (isPolling) startPolling()
    else stopPolling()
    return () => stopPolling()
  }, [isPolling])

  useEffect(() => {
    localStorage.setItem('visibleWidgets', JSON.stringify(visibleWidgets))
  }, [visibleWidgets])

  // ─── Helpers ──────────────────────────────────────────────────────
  const updateWidgetConfig = (widgetId, updates) => {
    setWidgetConfigs(prev => ({ ...prev, [widgetId]: { ...prev[widgetId], ...updates } }))
  }

  const toggleWidgetVisibility = (widgetId) => {
    setVisibleWidgets(prev => ({ ...prev, [widgetId]: !prev[widgetId] }))
  }

  const getFilteredTranscript = (widgetId) => {
    if (!meetingData || !meetingData.transcript) return []
    const config = widgetConfigs[widgetId]
    if (!config.participantFilter) return meetingData.transcript
    const participant = participants.find(p => p.id === config.participantFilter)
    if (!participant) return meetingData.transcript
    return meetingData.transcript.filter(entry => entry.nickname === participant.name)
  }

  const calculateStats = (transcript) => {
    if (!transcript || transcript.length === 0) {
      return {
        total_messages: 0,
        sentiment: { distribution: { positive: 0, neutral: 0, negative: 0 }, average_score: 0, positive_ratio: 0 },
        toxicity: { toxic_count: 0, toxic_ratio: 0, severity_distribution: { low: 0, medium: 0, high: 0 }, average_toxicity_score: 0 }
      }
    }
    const total = transcript.length
    let sentimentScoreSum = 0, toxicityScoreSum = 0
    const sentimentDist = { positive: 0, neutral: 0, negative: 0 }
    const severityDist = { low: 0, medium: 0, high: 0 }
    let toxicCount = 0

    transcript.forEach(entry => {
      const sentLabel = entry.sentiment.label
      if (sentimentDist[sentLabel] !== undefined) sentimentDist[sentLabel]++
      sentimentScoreSum += entry.sentiment.score
      if (entry.toxicity.is_toxic) toxicCount++
      const severity = entry.toxicity.severity
      if (severityDist[severity] !== undefined) severityDist[severity]++
      toxicityScoreSum += entry.toxicity.toxicity_score
    })

    return {
      total_messages: total,
      sentiment: { distribution: sentimentDist, average_score: sentimentScoreSum / total, positive_ratio: sentimentDist.positive / total },
      toxicity: { toxic_count: toxicCount, toxic_ratio: toxicCount / total, severity_distribution: severityDist, average_toxicity_score: toxicityScoreSum / total }
    }
  }

  // ─── Per-participant stats for roster ────────────────────────────
  const getParticipantStats = () => {
    if (!meetingData?.transcript || !participants.length) return []
    return participants.map(p => {
      const msgs = meetingData.transcript.filter(e => e.nickname === p.name)
      const stats = calculateStats(msgs)
      return { ...p, stats, msgCount: msgs.length }
    })
  }

  // ─── Widget sections (con descrizioni dettagliate) ────────────────
  const widgetSections = [
    {
      title: 'Participants',
      widgets: [
        {
          id: 'participantRoster',
          name: 'Participant Roster',
          description: 'Shows each participant\'s sentiment breakdown (positive / neutral / negative) and toxicity rate as individual stat cards — ideal for spotting who is driving the tone of the meeting.'
        }
      ]
    },
    {
      title: 'Key Metrics',
      widgets: [
        {
          id: 'messages',
          name: 'Messages',
          description: 'Displays the total number of messages exchanged in the meeting. Use the per-participant filter to count only one speaker\'s contributions.'
        },
        {
          id: 'sentiment',
          name: 'Sentiment Overview',
          description: 'Shows the average sentiment score (0 – 100 %) and the percentage of positive messages. A high score means the overall mood of the conversation is constructive.'
        },
        {
          id: 'toxicity',
          name: 'Toxic Messages',
          description: 'Counts how many messages were classified as toxic and what percentage of the total they represent. Toggle this off if your dataset contains no aggressive language.'
        }
      ]
    },
    {
      title: 'Analytics',
      widgets: [
        {
          id: 'sentimentDist',
          name: 'Sentiment Distribution',
          description: 'Horizontal stacked bar showing the proportion of positive, neutral and negative messages. Useful for a quick at-a-glance snapshot of the conversational balance.'
        },
        {
          id: 'timelineSentiment',
          name: 'Sentiment Timeline',
          description: 'Line chart plotting sentiment score over time (one point per message). Lets you identify emotional peaks, dips, and trends across the duration of the meeting.'
        },
        {
          id: 'timelineToxicity',
          name: 'Toxicity Timeline',
          description: 'Line chart plotting the toxicity score over time. Highlights moments when aggressive or inappropriate language spiked during the conversation.'
        },
        {
          id: 'toxicityGauge',
          name: 'Toxicity Severity',
          description: 'Doughnut gauge summarising the current average toxicity level (low / medium / high). Gives an immediate red-flag indicator without diving into the raw numbers.'
        }
      ]
    },
    {
      title: 'Content',
      widgets: [
        {
          id: 'messageStream',
          name: 'Message Stream',
          description: 'Scrollable feed of recent messages enriched with colour-coded sentiment and toxicity badges. The most recent messages appear at the top so you can follow the live conversation.'
        }
      ]
    }
  ]

  // ─── Formatted last-updated string ───────────────────────────────
  const formatTime = (date) => {
    if (!date) return '—'
    return date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  // ─── Render ───────────────────────────────────────────────────────
  return (
    <div style={styles.appContainer}>

      {/* ── HEADER ── */}
      <div style={styles.header}>
        <div style={styles.headerContent}>
          <div style={styles.headerLeft}>
            <div style={styles.logoCircle}>MI</div>
            <div style={styles.headerText}>
              <h1 style={styles.title}>Meeting Intelligence</h1>
              <p style={styles.subtitle}>MTG-001 · Unique Design</p>
            </div>
          </div>

          {/* Live indicator + controls */}
          <div style={styles.headerRight}>
            <div style={styles.liveBlock}>
              <div style={{ ...styles.liveDot, backgroundColor: isPolling ? '#34C759' : '#636366' }} />
              <span style={styles.liveLabel}>
                {isPolling ? `Auto-refresh in ${pollingCountdown}s` : 'Paused'}
              </span>
              {lastUpdated && (
                <span style={styles.lastUpdatedLabel}>· Updated {formatTime(lastUpdated)}</span>
              )}
            </div>

            <button
              onClick={() => setIsPolling(p => !p)}
              style={{ ...styles.controlBtn, backgroundColor: isPolling ? '#3a3a3c' : '#007AFF' }}
              title={isPolling ? 'Pause auto-refresh' : 'Resume auto-refresh'}
            >
              {isPolling ? '⏸' : '▶'}
            </button>

            <button
              onClick={() => loadInitialData(false)}
              style={{ ...styles.controlBtn, backgroundColor: '#3a3a3c' }}
              title="Refresh now"
            >
              ↻
            </button>

            <button onClick={() => setShowWidgetPanel(!showWidgetPanel)} style={styles.widgetToggleBtn}>
              <span style={styles.widgetToggleIcon}>⚙️</span>
              <span style={styles.widgetToggleText}>Customize</span>
            </button>
          </div>
        </div>
      </div>

      {/* ── CUSTOMIZE PANEL ── */}
      {showWidgetPanel && (
        <div style={styles.widgetPanelOverlay} onClick={() => setShowWidgetPanel(false)}>
          <div style={styles.widgetPanelContainer} onClick={(e) => e.stopPropagation()}>
            <div style={styles.widgetPanelHeader}>
              <h2 style={styles.widgetPanelTitle}>Customize Dashboard</h2>
              <button onClick={() => setShowWidgetPanel(false)} style={styles.widgetPanelCloseBtn}>Close</button>
            </div>

            <div style={styles.widgetPanelContent}>
              {widgetSections.map((section, sectionIdx) => (
                <div key={section.title} style={styles.widgetSection}>
                  <div style={styles.sectionHeader}>{section.title}</div>
                  <div style={styles.sectionContent}>
                    {section.widgets.map((widget, widgetIdx) => (
                      <div key={widget.id}>
                        <div
                          style={styles.widgetRow}
                          onClick={() => toggleWidgetVisibility(widget.id)}
                        >
                          <div style={styles.widgetRowLeft}>
                            <div style={styles.widgetRowTitle}>{widget.name}</div>
                            <div style={styles.widgetRowDescription}>{widget.description}</div>
                          </div>
                          <div style={styles.widgetRowRight}>
                            <button
                              style={{
                                ...styles.uniqueToggle,
                                backgroundColor: visibleWidgets[widget.id] ? '#007AFF' : '#3a3a3c',
                                color: visibleWidgets[widget.id] ? '#fff' : '#8e8e93'
                              }}
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleWidgetVisibility(widget.id)
                              }}
                            >
                              <span style={styles.toggleText}>
                                {visibleWidgets[widget.id] ? 'ON' : 'OFF'}
                              </span>
                            </button>
                          </div>
                        </div>
                        {widgetIdx < section.widgets.length - 1 && <div style={styles.separator} />}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <div style={styles.widgetPanelFooter}>
                <p style={styles.footerText}>
                  {Object.values(visibleWidgets).filter(Boolean).length} of {Object.keys(visibleWidgets).length} widgets enabled
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── ERROR ── */}
      {error && (
        <div style={styles.errorBanner}>
          <span style={styles.errorIcon}>!</span>
          <span>{error}</span>
        </div>
      )}

      {/* ── LOADING ── */}
      {loading && (
        <div style={styles.loadingContainer}>
          <div style={styles.spinner}></div>
          <p style={styles.loadingText}>Loading...</p>
        </div>
      )}

      {/* ── WIDGET GRID ── */}
      {!loading && meetingData && (
        <div style={styles.widgetGrid}>

          {/* Participant Roster — full width */}
          {visibleWidgets.participantRoster && (
            <CustomizableWidget
              widgetId="participantRoster"
              title="Participant Roster"
              config={widgetConfigs.participantRoster}
              participants={participants}
              onConfigChange={(u) => updateWidgetConfig('participantRoster', u)}
              openSettings={openSettings}
              setOpenSettings={setOpenSettings}
              wide
            >
              <ParticipantRoster participantStats={getParticipantStats()} />
            </CustomizableWidget>
          )}

          {visibleWidgets.messages && (
            <CustomizableWidget widgetId="messages" title="Messages" config={widgetConfigs.messages} participants={participants} onConfigChange={(u) => updateWidgetConfig('messages', u)} openSettings={openSettings} setOpenSettings={setOpenSettings}>
              {(() => {
                const data = getFilteredTranscript('messages')
                return <><div style={styles.kpiValue}>{data.length}</div><div style={styles.kpiLabel}>Total messages</div></>
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.sentiment && (
            <CustomizableWidget widgetId="sentiment" title="Sentiment" config={widgetConfigs.sentiment} participants={participants} onConfigChange={(u) => updateWidgetConfig('sentiment', u)} openSettings={openSettings} setOpenSettings={setOpenSettings}>
              {(() => {
                const data = getFilteredTranscript('sentiment')
                const stats = calculateStats(data)
                return <><div style={styles.kpiValue}>{(stats.sentiment.average_score * 100).toFixed(0)}%</div><div style={styles.kpiLabel}>{(stats.sentiment.positive_ratio * 100).toFixed(0)}% positive</div></>
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.toxicity && (
            <CustomizableWidget widgetId="toxicity" title="Toxic Messages" config={widgetConfigs.toxicity} participants={participants} onConfigChange={(u) => updateWidgetConfig('toxicity', u)} openSettings={openSettings} setOpenSettings={setOpenSettings}>
              {(() => {
                const data = getFilteredTranscript('toxicity')
                const stats = calculateStats(data)
                return <><div style={styles.kpiValue}>{stats.toxicity.toxic_count}</div><div style={styles.kpiLabel}>{(stats.toxicity.toxic_ratio * 100).toFixed(0)}% toxic</div></>
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.sentimentDist && (
            <CustomizableWidget widgetId="sentimentDist" title="Sentiment Distribution" config={widgetConfigs.sentimentDist} participants={participants} onConfigChange={(u) => updateWidgetConfig('sentimentDist', u)} openSettings={openSettings} setOpenSettings={setOpenSettings} wide>
              {(() => {
                const data = getFilteredTranscript('sentimentDist')
                const stats = calculateStats(data)
                return <SentimentDistributionChartJS data={stats.sentiment.distribution} config={widgetConfigs.sentimentDist} />
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.timelineSentiment && (
            <CustomizableWidget widgetId="timelineSentiment" title="Sentiment Timeline" config={widgetConfigs.timelineSentiment} participants={participants} onConfigChange={(u) => updateWidgetConfig('timelineSentiment', u)} openSettings={openSettings} setOpenSettings={setOpenSettings} wide>
              {(() => {
                const data = getFilteredTranscript('timelineSentiment')
                return <TimelineChartJS messages={data} config={widgetConfigs.timelineSentiment} />
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.timelineToxicity && (
            <CustomizableWidget widgetId="timelineToxicity" title="Toxicity Timeline" config={widgetConfigs.timelineToxicity} participants={participants} onConfigChange={(u) => updateWidgetConfig('timelineToxicity', u)} openSettings={openSettings} setOpenSettings={setOpenSettings} wide>
              {(() => {
                const data = getFilteredTranscript('timelineToxicity')
                return <TimelineChartJS messages={data} config={widgetConfigs.timelineToxicity} />
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.toxicityGauge && (
            <CustomizableWidget widgetId="toxicityGauge" title="Toxicity Severity" config={widgetConfigs.toxicityGauge} participants={participants} onConfigChange={(u) => updateWidgetConfig('toxicityGauge', u)} openSettings={openSettings} setOpenSettings={setOpenSettings}>
              {(() => {
                const data = getFilteredTranscript('toxicityGauge')
                const stats = calculateStats(data)
                return <ToxicityGaugeChartJS score={stats.toxicity.average_toxicity_score} config={widgetConfigs.toxicityGauge} />
              })()}
            </CustomizableWidget>
          )}

          {visibleWidgets.messageStream && (
            <CustomizableWidget widgetId="messageStream" title="Message Stream" config={widgetConfigs.messageStream} participants={participants} onConfigChange={(u) => updateWidgetConfig('messageStream', u)} openSettings={openSettings} setOpenSettings={setOpenSettings} wide>
              {(() => {
                const data = getFilteredTranscript('messageStream')
                return <MessageStream messages={data.slice(0, widgetConfigs.messageStream.limit)} config={widgetConfigs.messageStream} />
              })()}
            </CustomizableWidget>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// PARTICIPANT ROSTER COMPONENT
// ─────────────────────────────────────────────────────────────────────────────
function ParticipantRoster({ participantStats }) {
  if (!participantStats || participantStats.length === 0) {
    return <div style={styles.emptyState}>No participant data available</div>
  }

  const AVATAR_COLORS = ['#5856D6', '#007AFF', '#34C759', '#FF9500', '#FF2D55', '#BF5AF2']

  return (
    <div style={rosterStyles.grid}>
      {participantStats.map((p, idx) => {
        const s = p.stats
        const total = s.total_messages
        const dist = s.sentiment.distribution
        const posW = total ? (dist.positive / total) * 100 : 0
        const neuW = total ? (dist.neutral  / total) * 100 : 0
        const negW = total ? (dist.negative / total) * 100 : 0
        const avgSent = (s.sentiment.average_score * 100).toFixed(0)
        const toxRatio = total ? (s.toxicity.toxic_count / total * 100).toFixed(0) : 0
        const avatarColor = AVATAR_COLORS[idx % AVATAR_COLORS.length]

        // Dominant sentiment label + color
        let domSentLabel = 'neutral', domSentColor = '#FFCC00'
        if (dist.positive >= dist.neutral && dist.positive >= dist.negative) {
          domSentLabel = 'positive'; domSentColor = '#34C759'
        } else if (dist.negative > dist.positive && dist.negative >= dist.neutral) {
          domSentLabel = 'negative'; domSentColor = '#FF3B30'
        }

        return (
          <div key={p.id} style={rosterStyles.card}>
            {/* Avatar + name */}
            <div style={rosterStyles.cardHeader}>
              <div style={{ ...rosterStyles.avatar, backgroundColor: avatarColor }}>
                {p.name.slice(0, 2).toUpperCase()}
              </div>
              <div>
                <div style={rosterStyles.name}>{p.name}</div>
                <div style={{ ...rosterStyles.dominantBadge, backgroundColor: domSentColor + '22', color: domSentColor }}>
                  {domSentLabel}
                </div>
              </div>
            </div>

            {/* Sentiment bar */}
            <div style={rosterStyles.barLabel}>Sentiment breakdown</div>
            <div style={rosterStyles.barTrack}>
              {posW > 0 && <div style={{ ...rosterStyles.barSegment, width: `${posW}%`, backgroundColor: '#34C759' }} title={`Positive: ${dist.positive}`} />}
              {neuW > 0 && <div style={{ ...rosterStyles.barSegment, width: `${neuW}%`, backgroundColor: '#FFCC00' }} title={`Neutral: ${dist.neutral}`} />}
              {negW > 0 && <div style={{ ...rosterStyles.barSegment, width: `${negW}%`, backgroundColor: '#FF3B30' }} title={`Negative: ${dist.negative}`} />}
            </div>
            <div style={rosterStyles.barLegend}>
              <span style={rosterStyles.legendItem}><span style={{ color: '#34C759' }}>●</span> {dist.positive}</span>
              <span style={rosterStyles.legendItem}><span style={{ color: '#FFCC00' }}>●</span> {dist.neutral}</span>
              <span style={rosterStyles.legendItem}><span style={{ color: '#FF3B30' }}>●</span> {dist.negative}</span>
            </div>

            {/* KPIs row */}
            <div style={rosterStyles.kpiRow}>
              <div style={rosterStyles.kpiCell}>
                <div style={rosterStyles.kpiVal}>{total}</div>
                <div style={rosterStyles.kpiLab}>messages</div>
              </div>
              <div style={rosterStyles.kpiCell}>
                <div style={{ ...rosterStyles.kpiVal, color: '#34C759' }}>{avgSent}%</div>
                <div style={rosterStyles.kpiLab}>avg sentiment</div>
              </div>
              <div style={rosterStyles.kpiCell}>
                <div style={{ ...rosterStyles.kpiVal, color: s.toxicity.toxic_count > 0 ? '#FF3B30' : '#34C759' }}>
                  {toxRatio}%
                </div>
                <div style={rosterStyles.kpiLab}>toxic rate</div>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const rosterStyles = {
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
    gap: '16px',
    padding: '4px 0'
  },
  card: {
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderRadius: '14px',
    padding: '16px',
    border: '1px solid rgba(255,255,255,0.08)',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px'
  },
  cardHeader: { display: 'flex', alignItems: 'center', gap: '12px' },
  avatar: {
    width: '40px', height: '40px', borderRadius: '50%',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontWeight: '700', fontSize: '14px', color: '#fff', flexShrink: 0
  },
  name: { fontSize: '15px', fontWeight: '600', color: '#fff' },
  dominantBadge: {
    display: 'inline-block', marginTop: '3px',
    fontSize: '10px', fontWeight: '600', textTransform: 'uppercase',
    letterSpacing: '0.5px', padding: '2px 7px', borderRadius: '6px'
  },
  barLabel: { fontSize: '11px', color: '#8e8e93', marginBottom: '2px' },
  barTrack: {
    display: 'flex', height: '8px', borderRadius: '4px', overflow: 'hidden',
    backgroundColor: 'rgba(255,255,255,0.07)'
  },
  barSegment: { height: '100%', transition: 'width 0.5s ease' },
  barLegend: { display: 'flex', gap: '10px' },
  legendItem: { fontSize: '11px', color: '#8e8e93', display: 'flex', alignItems: 'center', gap: '3px' },
  kpiRow: {
    display: 'flex', justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: '10px', padding: '10px 8px'
  },
  kpiCell: { display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 },
  kpiVal: { fontSize: '16px', fontWeight: '700', color: '#fff' },
  kpiLab: { fontSize: '9px', color: '#636366', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.4px' }
}

// ─────────────────────────────────────────────────────────────────────────────
// CUSTOMIZABLE WIDGET WRAPPER
// ─────────────────────────────────────────────────────────────────────────────
function CustomizableWidget({ widgetId, title, children, config, participants, onConfigChange, openSettings, setOpenSettings, wide }) {
  const isOpen = openSettings === widgetId
  return (
    <div style={{ ...styles.widget, ...(wide ? styles.widgetWide : {}) }}>
      <div style={styles.widgetHeader}>
        <span style={styles.widgetTitle}>{title}</span>
        <button onClick={() => setOpenSettings(isOpen ? null : widgetId)} style={styles.settingsButton}>{isOpen ? '✕' : '⋯'}</button>
      </div>
      {isOpen && <WidgetSettings config={config} participants={participants} onConfigChange={onConfigChange} />}
      <div style={styles.widgetContent}>{children}</div>
    </div>
  )
}

function WidgetSettings({ config, participants, onConfigChange }) {
  return (
    <div style={styles.settingsPanel}>
      <div style={styles.settingRow}>
        <span style={styles.settingLabel}>Filter</span>
        <select value={config.participantFilter || ''} onChange={(e) => onConfigChange({ participantFilter: e.target.value || null })} style={styles.settingSelect}>
          <option value="">All</option>
          {participants.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CHART COMPONENTS (unchanged)
// ─────────────────────────────────────────────────────────────────────────────
function SentimentDistributionChartJS({ data, config }) {
  if (!data) return <div style={styles.emptyState}>No data</div>
  const total = (data.positive || 0) + (data.neutral || 0) + (data.negative || 0)
  if (total === 0) return <div style={styles.emptyState}>No data</div>
  return (
    <div style={{ height: '150px' }}>
      <Bar
        data={{ labels: ['Distribution'], datasets: [
          { label: 'Positive', data: [data.positive || 0], backgroundColor: '#34C759', borderRadius: 8 },
          { label: 'Neutral',  data: [data.neutral  || 0], backgroundColor: '#FFCC00', borderRadius: 8 },
          { label: 'Negative', data: [data.negative || 0], backgroundColor: '#FF3B30', borderRadius: 8 }
        ]}}
        options={{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: config.showLabels, position: 'bottom', labels: { color: '#8e8e93', padding: 10, font: { size: 11 } } }, tooltip: { backgroundColor: 'rgba(28,28,30,0.95)', callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.x} (${((ctx.parsed.x/total)*100).toFixed(0)}%)` } } }, scales: { x: { stacked: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8e8e93' } }, y: { stacked: true, display: false } }, animation: { duration: config.animated ? 500 : 0 } }}
      />
    </div>
  )
}

function TimelineChartJS({ messages, config }) {
  if (!messages || messages.length === 0) return <div style={styles.emptyState}>No data</div>
  const formatTime = (ts) => { const parts = ts.split(':'); return `${parseInt(parts[1])}:${parts[2].split('.')[0].padStart(2, '0')}` }
  const dataPoints = messages.map((msg, idx) => ({ x: idx, y: config.metric === 'sentiment' ? msg.sentiment.score : msg.toxicity.toxicity_score, timestamp: msg.from, formattedTime: formatTime(msg.from), nickname: msg.nickname, text: msg.text }))
  const xLabels = dataPoints.map((dp, idx) => { const step = Math.max(1, Math.floor(messages.length / 10)); return (idx === 0 || idx === messages.length - 1 || idx % step === 0) ? dp.formattedTime : '' })
  const chartColor = config.color || (config.metric === 'sentiment' ? '#00C7BE' : '#FF6B6B')
  return (
    <div style={{ height: '280px' }}>
      <Line
        data={{ labels: xLabels, datasets: [{ label: config.metric === 'sentiment' ? 'Sentiment Score' : 'Toxicity Score', data: dataPoints.map(dp => dp.y), borderColor: chartColor, backgroundColor: config.showArea ? chartColor + '22' : 'transparent', borderWidth: 2, pointRadius: 3, pointHoverRadius: 6, pointBackgroundColor: chartColor, fill: config.showArea, tension: 0.4 }]}}
        options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { backgroundColor: 'rgba(28,28,30,0.95)', callbacks: { title: (items) => { const dp = dataPoints[items[0].dataIndex]; return `${dp.formattedTime} · ${dp.nickname}` }, label: (ctx) => `Score: ${ctx.parsed.y.toFixed(3)}`, afterLabel: (ctx) => { const dp = dataPoints[ctx.dataIndex]; return dp.text.length > 50 ? dp.text.substring(0, 50) + '...' : dp.text } } } }, scales: { x: { grid: { display: config.showGrid, color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8e8e93', maxRotation: 0 } }, y: { min: 0, max: 1, grid: { display: config.showGrid, color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8e8e93', callback: (v) => (v * 100).toFixed(0) + '%' } } }, animation: { duration: 300 } }}
      />
    </div>
  )
}

function ToxicityGaugeChartJS({ score, config }) {
  const pct = Math.min(Math.max(score || 0, 0), 1)
  const level = pct < 0.33 ? 'Low' : pct < 0.66 ? 'Medium' : 'High'
  const color = pct < 0.33 ? '#34C759' : pct < 0.66 ? '#FF9500' : '#FF3B30'
  return (
    <div style={{ height: '150px', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <Doughnut
        data={{ datasets: [{ data: [pct, 1 - pct], backgroundColor: [color, 'rgba(255,255,255,0.07)'], borderWidth: 0, circumference: 180, rotation: 270 }]}}
        options={{ responsive: true, maintainAspectRatio: false, cutout: '75%', plugins: { legend: { display: false }, tooltip: { enabled: false } }, animation: { duration: 500 } }}
      />
      <div style={{ position: 'absolute', bottom: '10px', textAlign: 'center' }}>
        <div style={{ fontSize: '22px', fontWeight: '700', color }}>{(pct * 100).toFixed(0)}%</div>
        <div style={{ fontSize: '11px', color: '#8e8e93', marginTop: '2px' }}>{level} toxicity</div>
      </div>
    </div>
  )
}

function MessageStream({ messages, config }) {
  if (!messages || messages.length === 0) return <div style={styles.emptyState}>No messages</div>
  const sentimentColor = (label) => ({ positive: '#34C759', neutral: '#FFCC00', negative: '#FF3B30' }[label] || '#8e8e93')
  const formatTime = (ts) => { const parts = ts.split(':'); return `${parseInt(parts[1])}:${parts[2].split('.')[0].padStart(2, '0')}` }
  return (
    <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
      {[...messages].reverse().map((msg, idx) => (
        <div key={idx} style={msgStyles.row}>
          <div style={msgStyles.meta}>
            <span style={msgStyles.nick}>{msg.nickname}</span>
            {config.showTimestamps && <span style={msgStyles.time}>{formatTime(msg.from)}</span>}
            <span style={{ ...msgStyles.badge, backgroundColor: sentimentColor(msg.sentiment.label) + '22', color: sentimentColor(msg.sentiment.label) }}>
              {msg.sentiment.label}
            </span>
            {msg.toxicity.is_toxic && (
              <span style={{ ...msgStyles.badge, backgroundColor: '#FF3B3022', color: '#FF3B30' }}>
                ⚠ {msg.toxicity.severity}
              </span>
            )}
          </div>
          <div style={msgStyles.text}>{msg.text}</div>
        </div>
      ))}
    </div>
  )
}

const msgStyles = {
  row: { padding: '10px 0', borderBottom: '0.5px solid rgba(255,255,255,0.06)' },
  meta: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' },
  nick: { fontSize: '12px', fontWeight: '600', color: '#fff' },
  time: { fontSize: '11px', color: '#636366' },
  badge: { fontSize: '10px', fontWeight: '600', padding: '2px 7px', borderRadius: '6px', textTransform: 'uppercase', letterSpacing: '0.3px' },
  text: { fontSize: '13px', color: '#ebebf5cc', lineHeight: '1.5' }
}

// ─────────────────────────────────────────────────────────────────────────────
// STYLES
// ─────────────────────────────────────────────────────────────────────────────
const styles = {
  appContainer: { minHeight: '100vh', width: '100%', backgroundColor: '#1c1c1e', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif', color: '#fff', overflowX: 'hidden', position: 'relative' },

  // Header
  header: { position: 'sticky', top: 0, left: 0, right: 0, zIndex: 100, backgroundColor: 'rgba(28,28,30,0.95)', backdropFilter: 'saturate(180%) blur(20px)', WebkitBackdropFilter: 'saturate(180%) blur(20px)', borderBottom: '0.5px solid rgba(255,255,255,0.1)', padding: 'clamp(0.5rem,2vw,0.75rem) clamp(0.75rem,3vw,1rem)', boxShadow: '0 2px 10px rgba(0,0,0,0.3)' },
  headerContent: { maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 'clamp(0.5rem,2vw,0.75rem)', flex: '1 1 auto' },
  headerRight: { display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' },

  logoCircle: { width: '36px', height: '36px', borderRadius: '50%', background: 'linear-gradient(135deg,#007AFF,#5856D6)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '13px', fontWeight: '700', color: '#fff', flexShrink: 0 },
  headerText: {},
  title: { fontSize: 'clamp(15px,3vw,18px)', fontWeight: '700', color: '#fff', margin: 0 },
  subtitle: { fontSize: 'clamp(10px,2vw,12px)', color: '#8e8e93', margin: 0 },

  // Live indicator
  liveBlock: { display: 'flex', alignItems: 'center', gap: '6px' },
  liveDot: { width: '8px', height: '8px', borderRadius: '50%', animation: 'pulse 2s infinite' },
  liveLabel: { fontSize: '12px', color: '#8e8e93', fontVariantNumeric: 'tabular-nums' },
  lastUpdatedLabel: { fontSize: '11px', color: '#636366' },

  // Control buttons
  controlBtn: { border: 'none', borderRadius: '8px', padding: '6px 10px', fontSize: '14px', color: '#fff', cursor: 'pointer', transition: 'opacity 0.15s' },

  // Widget toggle
  widgetToggleBtn: { display: 'flex', alignItems: 'center', gap: '6px', backgroundColor: 'rgba(255,255,255,0.1)', border: '0.5px solid rgba(255,255,255,0.2)', borderRadius: '10px', padding: '8px 14px', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: '500', transition: 'background-color 0.2s' },
  widgetToggleIcon: { fontSize: '14px' },
  widgetToggleText: { fontSize: '13px' },

  // Grid
  widgetGrid: { maxWidth: '1400px', margin: '0 auto', padding: 'clamp(1rem,3vw,1.5rem)', display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 'clamp(0.75rem,2vw,1rem)', alignItems: 'start' },

  // Widget
  widget: { backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: '16px', border: '0.5px solid rgba(255,255,255,0.1)', overflow: 'hidden', transition: 'border-color 0.2s' },
  widgetWide: { gridColumn: '1 / -1' },
  widgetHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 16px 0' },
  widgetTitle: { fontSize: '13px', fontWeight: '600', color: '#8e8e93', textTransform: 'uppercase', letterSpacing: '0.5px' },
  settingsButton: { background: 'none', border: 'none', color: '#636366', cursor: 'pointer', fontSize: '18px', padding: '0 4px', lineHeight: 1 },
  widgetContent: { padding: '12px 16px 16px' },

  // KPI
  kpiValue: { fontSize: 'clamp(28px,5vw,40px)', fontWeight: '700', color: '#fff', lineHeight: 1 },
  kpiLabel: { fontSize: '12px', color: '#8e8e93', marginTop: '4px' },

  // Settings panel
  settingsPanel: { margin: '0 16px', padding: '12px', backgroundColor: 'rgba(0,0,0,0.3)', borderRadius: '10px', marginBottom: '8px' },
  settingRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' },
  settingLabel: { fontSize: '12px', color: '#8e8e93' },
  settingSelect: { backgroundColor: 'rgba(255,255,255,0.1)', border: '0.5px solid rgba(255,255,255,0.15)', borderRadius: '8px', color: '#fff', padding: '4px 8px', fontSize: '12px', flex: 1 },

  // Overlay panel
  widgetPanelOverlay: { position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 200, display: 'flex', justifyContent: 'flex-end' },
  widgetPanelContainer: { width: 'clamp(300px,90vw,420px)', height: '100%', backgroundColor: '#1c1c1e', borderLeft: '0.5px solid rgba(255,255,255,0.1)', display: 'flex', flexDirection: 'column', overflowY: 'auto' },
  widgetPanelHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '20px 20px 16px', borderBottom: '0.5px solid rgba(255,255,255,0.08)', position: 'sticky', top: 0, backgroundColor: '#1c1c1e', zIndex: 1 },
  widgetPanelTitle: { fontSize: '17px', fontWeight: '700', color: '#fff', margin: 0 },
  widgetPanelCloseBtn: { background: 'none', border: 'none', color: '#007AFF', cursor: 'pointer', fontSize: '15px', fontWeight: '500' },
  widgetPanelContent: { padding: '8px 0', flex: 1 },
  widgetPanelFooter: { padding: '12px 20px', borderTop: '0.5px solid rgba(255,255,255,0.08)', position: 'sticky', bottom: 0, backgroundColor: '#1c1c1e' },
  footerText: { fontSize: '12px', color: '#636366', margin: 0, textAlign: 'center' },

  // Widget section in panel
  widgetSection: { marginBottom: '8px' },
  sectionHeader: { fontSize: '11px', fontWeight: '600', color: '#636366', textTransform: 'uppercase', letterSpacing: '0.8px', padding: '12px 20px 6px' },
  sectionContent: { backgroundColor: 'rgba(255,255,255,0.03)', marginHorizontal: '16px' },

  widgetRow: { display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '14px 20px', cursor: 'pointer', gap: '12px' },
  widgetRowLeft: { flex: 1, minWidth: 0 },
  widgetRowTitle: { fontSize: '14px', fontWeight: '500', color: '#fff', marginBottom: '4px' },
  widgetRowDescription: { fontSize: '12px', color: '#8e8e93', lineHeight: '1.45' },
  widgetRowRight: { flexShrink: 0 },

  uniqueToggle: { border: 'none', borderRadius: '8px', padding: '5px 12px', cursor: 'pointer', transition: 'background-color 0.2s, color 0.2s', fontWeight: '600' },
  toggleText: { fontSize: '12px' },
  separator: { height: '0.5px', backgroundColor: 'rgba(255,255,255,0.06)', margin: '0 20px' },

  // States
  loadingContainer: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60vh', gap: '16px' },
  spinner: { width: '32px', height: '32px', border: '3px solid rgba(255,255,255,0.1)', borderTop: '3px solid #007AFF', borderRadius: '50%', animation: 'spin 1s linear infinite' },
  loadingText: { color: '#8e8e93', fontSize: '14px' },
  errorBanner: { display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: 'rgba(255,59,48,0.15)', border: '0.5px solid rgba(255,59,48,0.3)', borderRadius: '10px', padding: '12px 16px', margin: '16px', color: '#FF3B30', fontSize: '14px' },
  errorIcon: { fontWeight: '700', fontSize: '16px' },
  emptyState: { color: '#636366', fontSize: '13px', textAlign: 'center', padding: '20px 0' }
}

export default App