import { useState, useEffect } from 'react'
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

function App() {
  const [meetingData, setMeetingData] = useState(null)
  const [participants, setParticipants] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [widgetConfigs, setWidgetConfigs] = useState({
    messages: { participantFilter: null, color: '#FF3B30', showDetails: true },
    sentiment: { participantFilter: null, color: '#34C759', showDetails: true },
    toxicity: { participantFilter: null, color: '#FF9500', showDetails: true },
    sentimentDist: { participantFilter: null, color: '#007AFF', showLabels: true, animated: true },
    toxicityGauge: { participantFilter: null, color: '#5856D6', showDetails: true },
    timelineSentiment: { participantFilter: null, color: '#00C7BE', showGrid: true, showArea: true, metric: 'sentiment' },
    timelineToxicity: { participantFilter: null, color: '#FF6B6B', showGrid: true, showArea: true, metric: 'toxicity' },
    messageStream: { participantFilter: null, color: '#FF2D55', limit: 30, showTimestamps: true }
  })

  const [visibleWidgets, setVisibleWidgets] = useState(() => {
    const saved = localStorage.getItem('visibleWidgets')
    return saved ? JSON.parse(saved) : {
      messages: true, sentiment: true, toxicity: true, sentimentDist: true,
      toxicityGauge: true, timelineSentiment: true, timelineToxicity: true, messageStream: true
    }
  })

  const [openSettings, setOpenSettings] = useState(null)
  const [showWidgetPanel, setShowWidgetPanel] = useState(false)

  useEffect(() => { loadInitialData() }, [])
  useEffect(() => { localStorage.setItem('visibleWidgets', JSON.stringify(visibleWidgets)) }, [visibleWidgets])

  const loadInitialData = async () => {
    setLoading(true)
    try {
      const respPart = await fetch(`${API_URL}/participants`)
      const dataPart = await respPart.json()
      setParticipants(dataPart.participants)

      const response = await fetch(`${API_URL}/meeting/mtg001/analysis`)
      if (!response.ok) throw new Error(`Status ${response.status}`)
      const data = await response.json()
      setMeetingData(data)
      setError(null)
    } catch (err) {
      setError('Unable to load meeting data')
    } finally {
      setLoading(false)
    }
  }

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

  const widgetSections = [
    {
      title: 'Key Metrics',
      widgets: [
        { id: 'messages', name: 'Messages', description: 'Total message count' },
        { id: 'sentiment', name: 'Sentiment Overview', description: 'Average sentiment score' },
        { id: 'toxicity', name: 'Toxic Messages', description: 'Toxic message count' }
      ]
    },
    {
      title: 'Analytics',
      widgets: [
        { id: 'sentimentDist', name: 'Sentiment Distribution', description: 'Breakdown by category' },
        { id: 'timelineSentiment', name: 'Sentiment Timeline', description: 'Sentiment over time' },
        { id: 'timelineToxicity', name: 'Toxicity Timeline', description: 'Toxicity over time' },
        { id: 'toxicityGauge', name: 'Toxicity Severity', description: 'Current toxicity level' }
      ]
    },
    {
      title: 'Content',
      widgets: [
        { id: 'messageStream', name: 'Message Stream', description: 'Recent messages feed' }
      ]
    }
  ]

  return (
    <div style={styles.appContainer}>
      <div style={styles.header}>
        <div style={styles.headerContent}>
          <div style={styles.headerLeft}>
            <div style={styles.logoCircle}>MI</div>
            <div style={styles.headerText}>
              <h1 style={styles.title}>Meeting Intelligence</h1>
              <p style={styles.subtitle}>MTG-001 · Unique Design</p>
            </div>
          </div>
          
          <button onClick={() => setShowWidgetPanel(!showWidgetPanel)} style={styles.widgetToggleBtn}>
            <span style={styles.widgetToggleIcon}>⚙️</span>
            <span style={styles.widgetToggleText}>Customize</span>
          </button>
        </div>
      </div>

      {/* UNIQUE DESIGN WIDGET PANEL */}
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
                            {/* UNIQUE TOGGLE BUTTON - COMPLETELY ORIGINAL */}
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

      {error && (
        <div style={styles.errorBanner}>
          <span style={styles.errorIcon}>!</span>
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div style={styles.loadingContainer}>
          <div style={styles.spinner}></div>
          <p style={styles.loadingText}>Loading...</p>
        </div>
      )}

      {!loading && meetingData && (
        <div style={styles.widgetGrid}>
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

// Components (same but I'll include for completeness)
function SentimentDistributionChartJS({ data, config }) {
  if (!data) return <div style={styles.emptyState}>No data</div>
  const total = (data.positive || 0) + (data.neutral || 0) + (data.negative || 0)
  if (total === 0) return <div style={styles.emptyState}>No data</div>
  return (
    <div style={{ height: '150px' }}>
      <Bar 
        data={{ labels: ['Distribution'], datasets: [
          { label: 'Positive', data: [data.positive || 0], backgroundColor: '#34C759', borderRadius: 8 },
          { label: 'Neutral', data: [data.neutral || 0], backgroundColor: '#FFCC00', borderRadius: 8 },
          { label: 'Negative', data: [data.negative || 0], backgroundColor: '#FF3B30', borderRadius: 8 }
        ]}}
        options={{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: config.showLabels, position: 'bottom', labels: { color: '#8e8e93', padding: 10, font: { size: 11 } } }, tooltip: { backgroundColor: 'rgba(28, 28, 30, 0.95)', callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.x} (${((ctx.parsed.x/total)*100).toFixed(0)}%)` } } }, scales: { x: { stacked: true, grid: { color: 'rgba(255, 255, 255, 0.05)' }, ticks: { color: '#8e8e93' } }, y: { stacked: true, display: false } }, animation: { duration: config.animated ? 500 : 0 } }}
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
      <Line data={{ labels: xLabels, datasets: [{ label: config.metric === 'sentiment' ? 'Sentiment' : 'Toxicity', data: dataPoints.map(p => p.y), borderColor: chartColor, backgroundColor: config.showArea ? chartColor + '30' : 'transparent', borderWidth: 3, fill: config.showArea, tension: 0.4, pointRadius: 4, pointHoverRadius: 6 }] }} options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { backgroundColor: 'rgba(28, 28, 30, 0.95)', callbacks: { title: (ctx) => `${dataPoints[ctx[0].dataIndex].nickname} - ${dataPoints[ctx[0].dataIndex].timestamp}`, label: (ctx) => `${config.metric === 'sentiment' ? 'Sentiment' : 'Toxicity'}: ${(ctx.parsed.y * 100).toFixed(0)}%` } } }, scales: { x: { grid: { display: config.showGrid }, ticks: { autoSkip: false, font: { size: 9 } } }, y: { min: 0, max: 1, grid: { display: config.showGrid }, ticks: { callback: (v) => `${(v*100).toFixed(0)}%` } } } }} />
    </div>
  )
}

function ToxicityGaugeChartJS({ score, config }) {
  const safeScore = score ?? 0
  const getColor = () => safeScore < 0.3 ? '#34C759' : safeScore < 0.6 ? '#FFCC00' : '#FF3B30'
  const getLabel = () => safeScore < 0.3 ? 'LOW' : safeScore < 0.6 ? 'MEDIUM' : 'HIGH'
  return (
    <div style={styles.gaugeContainer}>
      <div style={{ height: '160px', position: 'relative' }}>
        <Doughnut data={{ datasets: [{ data: [safeScore * 100, (1 - safeScore) * 100], backgroundColor: [getColor(), 'rgba(255, 255, 255, 0.05)'], borderWidth: 0, circumference: 180, rotation: 270 }] }} options={{ responsive: true, maintainAspectRatio: false, cutout: '75%', plugins: { legend: { display: false }, tooltip: { enabled: false } } }} />
        <div style={{ position: 'absolute', top: '55%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center' }}>
          <div style={{ ...styles.gaugeValue, color: getColor() }}>{(safeScore * 100).toFixed(0)}%</div>
          <div style={styles.gaugeLabel}>{getLabel()}</div>
        </div>
      </div>
      {config.showDetails && (
        <div style={styles.gaugeDetails}>
          <div style={styles.detailItem}>
            <span style={styles.detailLabel}>Score</span>
            <span style={styles.detailValue}>{safeScore.toFixed(3)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function MessageStream({ messages, config }) {
  if (!messages || messages.length === 0) return <div style={styles.emptyState}>No messages</div>
  return <div style={styles.messageStreamContainer}>{messages.map((msg) => <MessageBubble key={msg.uid} message={msg} config={config} />)}</div>
}

function MessageBubble({ message, config }) {
  const getSentimentColor = (label) => ({ positive: '#34C759', neutral: '#FFCC00', negative: '#FF3B30' }[label] || '#8e8e93')
  const getToxicityBadge = (tox) => {
    const colors = { low: '#34C759', medium: '#FF9500', high: '#FF3B30' }
    return { text: tox.severity.toUpperCase(), color: colors[tox.severity] || '#8e8e93' }
  }
  const badge = getToxicityBadge(message.toxicity)
  return (
    <div style={styles.messageBubble}>
      <div style={styles.bubbleHeader}>
        <span style={styles.bubbleAuthor}>{message.nickname}</span>
        <div style={styles.bubbleBadges}>
          <span style={{ ...styles.sentimentBadge, backgroundColor: getSentimentColor(message.sentiment.label) }}>{(message.sentiment.score * 100).toFixed(0)}%</span>
          <span style={{ ...styles.toxicBadge, backgroundColor: badge.color }}>{badge.text}</span>
        </div>
      </div>
      <p style={styles.bubbleText}>{message.text}</p>
      {config.showTimestamps && <span style={styles.bubbleTime}>{message.from}</span>}
    </div>
  )
}

function CustomizableWidget({ widgetId, title, children, config, participants, onConfigChange, openSettings, setOpenSettings, wide }) {
  const isOpen = openSettings === widgetId
  return (
    <div style={{ ...styles.iosWidget, ...(wide && styles.wideWidget) }}>
      <div style={styles.widgetHeader}>
        <span style={styles.widgetTitle}>{title}</span>
        <div style={styles.headerActions}>
          <div style={{ ...styles.widgetDot, backgroundColor: config.color }} />
          <button onClick={() => setOpenSettings(isOpen ? null : widgetId)} style={styles.settingsButton}>{isOpen ? '✕' : '⋯'}</button>
        </div>
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

// UNIQUE DESIGN STYLES
const styles = {
  appContainer: { minHeight: '100vh', width: '100%', backgroundColor: '#1c1c1e', fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif', color: '#fff', overflowX: 'hidden', position: 'relative' },
  header: { position: 'sticky', top: 0, left: 0, right: 0, zIndex: 100, backgroundColor: 'rgba(28, 28, 30, 0.95)', backdropFilter: 'saturate(180%) blur(20px)', WebkitBackdropFilter: 'saturate(180%) blur(20px)', borderBottom: '0.5px solid rgba(255, 255, 255, 0.1)', padding: 'clamp(0.5rem, 2vw, 0.75rem) clamp(0.75rem, 3vw, 1rem)', boxShadow: '0 2px 10px rgba(0, 0, 0, 0.3)' },
  headerContent: { maxWidth: '1400px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 'clamp(0.5rem, 2vw, 0.75rem)' },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 'clamp(0.5rem, 2vw, 0.75rem)', flex: '1 1 auto', minWidth: '0' },
  logoCircle: { width: 'clamp(32px, 8vw, 40px)', height: 'clamp(32px, 8vw, 40px)', borderRadius: 'clamp(8px, 2vw, 10px)', background: 'linear-gradient(135deg, #FF3B30 0%, #FF9500 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'clamp(0.85rem, 2.5vw, 1rem)', fontWeight: '700', flexShrink: 0 },
  headerText: { flex: '1', minWidth: '0', overflow: 'hidden' },
  title: { margin: 0, fontSize: 'clamp(0.85rem, 3.5vw, 1.25rem)', fontWeight: '700', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  subtitle: { margin: 0, fontSize: 'clamp(0.65rem, 2vw, 0.85rem)', color: '#8e8e93' },
  widgetToggleBtn: { padding: 'clamp(0.5rem, 2vw, 0.6rem) clamp(0.75rem, 3vw, 1rem)', borderRadius: 'clamp(8px, 2vw, 10px)', border: 'none', background: 'rgba(255, 255, 255, 0.1)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'clamp(0.75rem, 2vw, 0.85rem)', fontWeight: '600', transition: 'all 0.2s', flexShrink: 0, minWidth: '44px', minHeight: '44px', justifyContent: 'center' },
  widgetToggleIcon: { fontSize: 'clamp(0.95rem, 2.5vw, 1.1rem)' },
  widgetToggleText: { display: 'inline' },
  
  // PANEL
  widgetPanelOverlay: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0, 0, 0, 0.5)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', zIndex: 200, display: 'flex', alignItems: 'flex-end', justifyContent: 'center', animation: 'fadeIn 0.2s ease-out' },
  widgetPanelContainer: { width: '100%', maxWidth: '600px', maxHeight: '85vh', backgroundColor: '#1c1c1e', borderTopLeftRadius: '20px', borderTopRightRadius: '20px', boxShadow: '0 -4px 30px rgba(0, 0, 0, 0.6)', display: 'flex', flexDirection: 'column', animation: 'slideUp 0.3s cubic-bezier(0.32, 0.72, 0, 1)', margin: '0 1rem' },
  widgetPanelHeader: { padding: '1.25rem 1.5rem', borderBottom: '0.5px solid rgba(255, 255, 255, 0.1)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 },
  widgetPanelTitle: { margin: 0, fontSize: 'clamp(1.1rem, 3vw, 1.25rem)', fontWeight: '700', letterSpacing: '-0.02em' },
  widgetPanelCloseBtn: { padding: '0.5rem 1rem', borderRadius: '8px', border: 'none', background: '#007AFF', color: '#fff', fontSize: 'clamp(0.85rem, 2.5vw, 0.95rem)', fontWeight: '600', cursor: 'pointer', transition: 'opacity 0.2s' },
  widgetPanelContent: { flex: 1, overflowY: 'auto', padding: '1rem 0' },
  widgetSection: { marginBottom: '2rem' },
  sectionHeader: { padding: '0 1.5rem', fontSize: 'clamp(0.75rem, 2vw, 0.85rem)', fontWeight: '600', color: '#8e8e93', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '0.75rem' },
  sectionContent: { backgroundColor: '#2c2c2e', borderRadius: '12px', margin: '0 1rem', overflow: 'hidden' },
  widgetRow: { padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', cursor: 'pointer', transition: 'background-color 0.15s', minHeight: '68px' },
  widgetRowLeft: { flex: 1, minWidth: 0 },
  widgetRowTitle: { fontSize: 'clamp(0.9rem, 2.5vw, 1rem)', fontWeight: '500', color: '#fff', marginBottom: '0.25rem', letterSpacing: '-0.01em' },
  widgetRowDescription: { fontSize: 'clamp(0.75rem, 2vw, 0.85rem)', color: '#8e8e93', lineHeight: '1.4' },
  widgetRowRight: { flexShrink: 0 },
  
  // UNIQUE TOGGLE BUTTON - TEXT BASED (NOT APPLE!)
  uniqueToggle: {
    padding: '0.4rem 0.85rem',
    borderRadius: '6px',
    border: 'none',
    fontSize: 'clamp(0.7rem, 2vw, 0.8rem)',
    fontWeight: '700',
    letterSpacing: '0.5px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    minWidth: '50px',
    textAlign: 'center',
    textTransform: 'uppercase',
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.3)'
  },
  
  toggleText: {
    display: 'block'
  },
  
  separator: { height: '0.5px', backgroundColor: 'rgba(255, 255, 255, 0.08)', marginLeft: '1.25rem' },
  widgetPanelFooter: { padding: '1rem 1.5rem', borderTop: '0.5px solid rgba(255, 255, 255, 0.1)', flexShrink: 0 },
  footerText: { margin: 0, fontSize: 'clamp(0.75rem, 2vw, 0.85rem)', color: '#8e8e93', textAlign: 'center' },
  
  // Rest same
  widgetGrid: { maxWidth: '1400px', margin: '0 auto', padding: 'clamp(0.75rem, 2vw, 1rem)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(clamp(240px, 60vw, 280px), 1fr))', gap: 'clamp(0.75rem, 2vw, 1rem)', width: '100%', boxSizing: 'border-box' },
  iosWidget: { borderRadius: 'clamp(12px, 3vw, 16px)', padding: 'clamp(1rem, 2.5vw, 1.25rem)', backgroundColor: 'rgba(44, 44, 46, 0.6)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '0.5px solid rgba(255, 255, 255, 0.08)', boxShadow: '0 4px 16px rgba(0, 0, 0, 0.5)', transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)', minWidth: 0, overflow: 'hidden' },
  wideWidget: { gridColumn: 'span 2' },
  widgetHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'clamp(0.75rem, 2vw, 1rem)', paddingBottom: 'clamp(0.5rem, 1.5vw, 0.75rem)', borderBottom: '0.5px solid rgba(255, 255, 255, 0.06)', gap: '0.5rem' },
  widgetTitle: { fontSize: 'clamp(0.85rem, 2.5vw, 1.05rem)', fontWeight: '600', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 },
  headerActions: { display: 'flex', gap: 'clamp(0.4rem, 1.5vw, 0.5rem)', alignItems: 'center', flexShrink: 0 },
  widgetDot: { width: 'clamp(6px, 1.5vw, 8px)', height: 'clamp(6px, 1.5vw, 8px)', borderRadius: '50%', flexShrink: 0 },
  settingsButton: { width: 'clamp(28px, 7vw, 32px)', height: 'clamp(28px, 7vw, 32px)', borderRadius: 'clamp(6px, 2vw, 8px)', border: 'none', background: 'rgba(255, 255, 255, 0.08)', color: '#fff', fontSize: 'clamp(0.95rem, 2.5vw, 1.1rem)', fontWeight: '600', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  widgetContent: { display: 'flex', flexDirection: 'column', gap: 'clamp(0.75rem, 2vw, 1rem)' },
  kpiValue: { fontSize: 'clamp(1.5rem, 8vw, 3.5rem)', fontWeight: '700', color: '#fff', textAlign: 'center', lineHeight: '1', letterSpacing: '-0.03em' },
  kpiLabel: { fontSize: 'clamp(0.7rem, 2vw, 0.9rem)', fontWeight: '500', color: '#8e8e93', textAlign: 'center', marginTop: '0.5rem' },
  emptyState: { textAlign: 'center', padding: 'clamp(1.5rem, 4vw, 2rem) clamp(0.75rem, 2vw, 1rem)', color: '#8e8e93', fontSize: 'clamp(0.75rem, 2vw, 0.9rem)' },
  loadingContainer: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '60vh', gap: 'clamp(1rem, 3vw, 1.5rem)', padding: 'clamp(1.5rem, 4vw, 2rem)' },
  spinner: { width: 'clamp(40px, 10vw, 50px)', height: 'clamp(40px, 10vw, 50px)', border: '4px solid #3a3a3c', borderTop: '4px solid #007AFF', borderRadius: '50%', animation: 'spin 1s linear infinite' },
  loadingText: { fontSize: 'clamp(0.8rem, 2vw, 0.9rem)', fontWeight: '500', color: '#8e8e93' },
  errorBanner: { padding: 'clamp(0.75rem, 2vw, 1rem)', margin: 'clamp(0.75rem, 2vw, 1rem)', backgroundColor: '#3a3a3c', borderRadius: 'clamp(10px, 2.5vw, 12px)', display: 'flex', alignItems: 'center', gap: 'clamp(0.5rem, 1.5vw, 0.75rem)', fontSize: 'clamp(0.75rem, 2vw, 0.85rem)', color: '#FF3B30' },
  errorIcon: { width: 'clamp(20px, 5vw, 24px)', height: 'clamp(20px, 5vw, 24px)', borderRadius: '50%', backgroundColor: '#FF3B30', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: '700', flexShrink: 0, fontSize: 'clamp(0.75rem, 2vw, 0.9rem)' },
  settingsPanel: { marginBottom: 'clamp(0.75rem, 2vw, 1rem)', padding: 'clamp(0.75rem, 2vw, 1rem)', borderRadius: 'clamp(10px, 2.5vw, 12px)', backgroundColor: 'rgba(28, 28, 30, 0.8)', border: '0.5px solid rgba(255, 255, 255, 0.08)' },
  settingRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 'clamp(0.75rem, 2vw, 1rem)', padding: '0.5rem 0', flexWrap: 'wrap' },
  settingLabel: { fontSize: 'clamp(0.75rem, 2vw, 0.9rem)', fontWeight: '500', color: '#8e8e93' },
  settingSelect: { padding: 'clamp(0.4rem, 1.5vw, 0.5rem) clamp(0.6rem, 2vw, 0.75rem)', fontSize: 'clamp(0.7rem, 2vw, 0.85rem)', borderRadius: 'clamp(6px, 2vw, 8px)', border: '0.5px solid rgba(255, 255, 255, 0.1)', backgroundColor: 'rgba(44, 44, 46, 0.6)', color: '#fff', outline: 'none', fontWeight: '500', cursor: 'pointer', minWidth: '100px', minHeight: '36px' },
  gaugeContainer: { display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 'clamp(0.75rem, 2vw, 1rem)', padding: 'clamp(0.75rem, 2vw, 1rem) 0' },
  gaugeValue: { fontSize: 'clamp(1.75rem, 7vw, 2.75rem)', fontWeight: '700', letterSpacing: '-0.02em' },
  gaugeLabel: { fontSize: 'clamp(0.65rem, 1.8vw, 0.8rem)', fontWeight: '600', color: '#8e8e93', letterSpacing: '1.5px', marginTop: '0.25rem', textTransform: 'uppercase' },
  gaugeDetails: { width: '100%', display: 'flex', flexDirection: 'column', gap: '0.5rem' },
  detailItem: { display: 'flex', justifyContent: 'space-between', padding: 'clamp(0.6rem, 2vw, 0.75rem)', borderRadius: 'clamp(8px, 2vw, 10px)', backgroundColor: 'rgba(28, 28, 30, 0.6)', gap: 'clamp(0.75rem, 2vw, 1rem)', flexWrap: 'wrap' },
  detailLabel: { fontSize: 'clamp(0.7rem, 2vw, 0.85rem)', fontWeight: '500', color: '#8e8e93' },
  detailValue: { fontSize: 'clamp(0.8rem, 2vw, 0.95rem)', fontWeight: '600', color: '#fff' },
  messageStreamContainer: { display: 'flex', flexDirection: 'column', gap: 'clamp(0.6rem, 1.5vw, 0.75rem)', maxHeight: 'clamp(400px, 80vh, 500px)', overflowY: 'auto', paddingRight: '0.5rem' },
  messageBubble: { padding: 'clamp(0.75rem, 2vw, 0.875rem) clamp(0.875rem, 2.5vw, 1rem)', borderRadius: 'clamp(12px, 3vw, 14px)', backgroundColor: 'rgba(28, 28, 30, 0.6)', border: '0.5px solid rgba(255, 255, 255, 0.06)', boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)' },
  bubbleHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'clamp(0.4rem, 1.5vw, 0.5rem)', gap: '0.5rem', flexWrap: 'wrap' },
  bubbleAuthor: { fontSize: 'clamp(0.75rem, 2vw, 0.9rem)', fontWeight: '600', color: '#fff' },
  bubbleBadges: { display: 'flex', gap: 'clamp(0.4rem, 1.5vw, 0.5rem)', flexShrink: 0 },
  sentimentBadge: { fontSize: 'clamp(0.6rem, 1.5vw, 0.75rem)', fontWeight: '700', color: '#000', padding: 'clamp(0.2rem, 1vw, 0.25rem) clamp(0.4rem, 1.5vw, 0.5rem)', borderRadius: 'clamp(5px, 1.5vw, 6px)' },
  toxicBadge: { fontSize: 'clamp(0.55rem, 1.5vw, 0.7rem)', fontWeight: '700', color: '#fff', padding: 'clamp(0.2rem, 1vw, 0.25rem) clamp(0.4rem, 1.5vw, 0.5rem)', borderRadius: 'clamp(5px, 1.5vw, 6px)', textTransform: 'uppercase' },
  bubbleText: { margin: 0, fontSize: 'clamp(0.75rem, 2vw, 0.9rem)', lineHeight: '1.5', color: '#d1d1d6', wordBreak: 'break-word' },
  bubbleTime: { display: 'block', marginTop: 'clamp(0.4rem, 1.5vw, 0.5rem)', fontSize: 'clamp(0.6rem, 1.5vw, 0.75rem)', fontWeight: '500', color: '#636366' }
}

const styleSheet = document.createElement('style')
styleSheet.textContent = `
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUp { from { transform: translateY(100%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

.widget-row:hover { background-color: rgba(255, 255, 255, 0.05) !important; }
.widget-panel-close-btn:hover { opacity: 0.85; }
.unique-toggle:hover { filter: brightness(1.1); transform: scale(1.02); }
.unique-toggle:active { transform: scale(0.98); }

@media (max-width: 768px) {
  .widget-toggle-text { display: none !important; }
  .widget-panel-container { max-width: 100% !important; margin: 0 !important; border-radius: 20px 20px 0 0 !important; }
}

@media (max-width: 1024px) {
  .wide-widget { grid-column: span 1 !important; }
}

body, html { overflow-x: hidden !important; width: 100% !important; max-width: 100vw !important; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.05); border-radius: 3px; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.2); border-radius: 3px; }
`
document.head.appendChild(styleSheet)

export default App