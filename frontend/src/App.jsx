/**
 * Meeting Intelligence Dashboard
 * 
 * EDUCATIONAL NOTE FOR FUTURE STUDENTS:
 * This React app displays real-time sentiment and toxicity analysis of meeting transcripts.
 * It fetches data from the FastAPI backend and visualizes it using Chart.js.
 * 
 * Key features:
 * - Customizable widgets (filter by participant, toggle settings)
 * - Chart.js visualizations (bar, line, doughnut charts)
 * - Real-time timeline showing sentiment/toxicity evolution
 * - Message stream with color-coded badges
 * 
 * Architecture:
 * - React 18 with Hooks (useState, useEffect)
 * - Chart.js for visualizations
 * - Fetch API for backend communication
 */

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

// Register Chart.js components (required before using charts)
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

// Backend API URL (can be changed for production)
const API_URL = 'http://localhost:8000'

function App() {
  // ============================================
  // STATE MANAGEMENT
  // ============================================
  
  // Main data from backend
  const [meetingData, setMeetingData] = useState(null)
  const [participants, setParticipants] = useState([])
  
  // UI state
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  // Widget configurations (each widget has its own settings)
  const [widgetConfigs, setWidgetConfigs] = useState({
    messages: {
      participantFilter: null,
      color: '#FF3B30',
      showDetails: true
    },
    sentiment: {
      participantFilter: null,
      color: '#34C759',
      showDetails: true
    },
    toxicity: {
      participantFilter: null,
      color: '#FF9500',
      showDetails: true
    },
    sentimentDist: {
      participantFilter: null,
      color: '#007AFF',
      showLabels: true,
      animated: true
    },
    toxicityGauge: {
      participantFilter: null,
      color: '#5856D6',
      showDetails: true
    },
    timelineSentiment: {
      participantFilter: null,
      color: '#00C7BE',
      showGrid: true,
      showArea: true,
      metric: 'sentiment'
    },
    timelineToxicity: {
      participantFilter: null,
      color: '#FF6B6B',
      showGrid: true,
      showArea: true,
      metric: 'toxicity'
    },
    messageStream: {
      participantFilter: null,
      color: '#FF2D55',
      limit: 30,
      showTimestamps: true
    }
  })

  // Track which widget settings panel is open
  const [openSettings, setOpenSettings] = useState(null)

  // ============================================
  // DATA LOADING
  // ============================================
  
  useEffect(() => {
    // Load data when component mounts
    loadInitialData()
  }, [])

  const loadInitialData = async () => {
    setLoading(true)
    try {
      // Load participants list
      const respPart = await fetch(`${API_URL}/participants`)
      const dataPart = await respPart.json()
      setParticipants(dataPart.participants)

      // Load meeting transcript with sentiment + toxicity analysis
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

  // ============================================
  // WIDGET CONFIGURATION HELPERS
  // ============================================
  
  const updateWidgetConfig = (widgetId, updates) => {
    setWidgetConfigs(prev => ({
      ...prev,
      [widgetId]: { ...prev[widgetId], ...updates }
    }))
  }

  const getFilteredTranscript = (widgetId) => {
    /**
     * Filter transcript based on widget's participant filter.
     * If no filter is set, returns all messages.
     */
    if (!meetingData || !meetingData.transcript) return []
    
    const config = widgetConfigs[widgetId]
    if (!config.participantFilter) {
      return meetingData.transcript
    }

    const participant = participants.find(p => p.id === config.participantFilter)
    if (!participant) return meetingData.transcript

    return meetingData.transcript.filter(entry => 
      entry.nickname === participant.name
    )
  }

  const calculateStats = (transcript) => {
    /**
     * Calculate statistics from filtered transcript.
     * Used when participant filter is active (recalculates stats dynamically).
     */
    if (!transcript || transcript.length === 0) {
      return {
        total_messages: 0,
        sentiment: {
          distribution: { positive: 0, neutral: 0, negative: 0 },
          average_score: 0,
          positive_ratio: 0
        },
        toxicity: {
          toxic_count: 0,
          toxic_ratio: 0,
          severity_distribution: { low: 0, medium: 0, high: 0 },
          average_toxicity_score: 0
        }
      }
    }

    const total = transcript.length
    let sentimentScoreSum = 0
    let toxicityScoreSum = 0

    const sentimentDist = { positive: 0, neutral: 0, negative: 0 }
    const severityDist = { low: 0, medium: 0, high: 0 }
    let toxicCount = 0

    transcript.forEach(entry => {
      // Sentiment stats
      const sentLabel = entry.sentiment.label
      if (sentimentDist[sentLabel] !== undefined) {
        sentimentDist[sentLabel]++
      }
      sentimentScoreSum += entry.sentiment.score

      // Toxicity stats
      if (entry.toxicity.is_toxic) {
        toxicCount++
      }
      
      const severity = entry.toxicity.severity
      if (severityDist[severity] !== undefined) {
        severityDist[severity]++
      }
      
      toxicityScoreSum += entry.toxicity.toxicity_score
    })

    return {
      total_messages: total,
      sentiment: {
        distribution: sentimentDist,
        average_score: sentimentScoreSum / total,
        positive_ratio: sentimentDist.positive / total
      },
      toxicity: {
        toxic_count: toxicCount,
        toxic_ratio: toxicCount / total,
        severity_distribution: severityDist,
        average_toxicity_score: toxicityScoreSum / total
      }
    }
  }

  // ============================================
  // RENDER
  // ============================================
  
  return (
    <div style={styles.appContainer}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerContent}>
          <div style={styles.headerLeft}>
            <div style={styles.logoCircle}>MI</div>
            <div>
              <h1 style={styles.title}>Meeting Intelligence</h1>
              <p style={styles.subtitle}>MTG-001 ·</p>
            </div>
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={styles.errorBanner}>
          <span style={styles.errorIcon}>!</span>
          <span>{error}</span>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div style={styles.loadingContainer}>
          <div style={styles.spinner}></div>
          <p style={styles.loadingText}>Loading analytics...</p>
        </div>
      )}

      {/* Widget Grid */}
      {!loading && meetingData && (
        <div style={styles.widgetGrid}>
          {/* Messages Widget */}
          <CustomizableWidget
            widgetId="messages"
            title="Messages"
            config={widgetConfigs.messages}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('messages', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
          >
            {(() => {
              const data = getFilteredTranscript('messages')
              return (
                <>
                  <div style={styles.kpiValue}>{data.length}</div>
                  <div style={styles.kpiLabel}>Total messages</div>
                </>
              )
            })()}
          </CustomizableWidget>

          {/* Sentiment Widget */}
          <CustomizableWidget
            widgetId="sentiment"
            title="Sentiment"
            config={widgetConfigs.sentiment}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('sentiment', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
          >
            {(() => {
              const data = getFilteredTranscript('sentiment')
              const stats = calculateStats(data)
              return (
                <>
                  <div style={styles.kpiValue}>
                    {(stats.sentiment.average_score * 100).toFixed(0)}%
                  </div>
                  <div style={styles.kpiLabel}>
                    {(stats.sentiment.positive_ratio * 100).toFixed(0)}% positive
                  </div>
                </>
              )
            })()}
          </CustomizableWidget>

          {/* Toxicity Widget */}
          <CustomizableWidget
            widgetId="toxicity"
            title="Toxicity"
            config={widgetConfigs.toxicity}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('toxicity', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
          >
            {(() => {
              const data = getFilteredTranscript('toxicity')
              const stats = calculateStats(data)
              return (
                <>
                  <div style={styles.kpiValue}>
                    {stats.toxicity.toxic_count}
                  </div>
                  <div style={styles.kpiLabel}>
                    {(stats.toxicity.toxic_ratio * 100).toFixed(0)}% toxic rate
                  </div>
                </>
              )
            })()}
          </CustomizableWidget>

          {/* Sentiment Distribution Chart */}
          <CustomizableWidget
            widgetId="sentimentDist"
            title="Sentiment Distribution"
            config={widgetConfigs.sentimentDist}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('sentimentDist', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
            wide
          >
            {(() => {
              const data = getFilteredTranscript('sentimentDist')
              const stats = calculateStats(data)
              return (
                <SentimentDistributionChartJS
                  data={stats.sentiment.distribution}
                  config={widgetConfigs.sentimentDist}
                />
              )
            })()}
          </CustomizableWidget>

          {/* Sentiment Timeline */}
          <CustomizableWidget
            widgetId="timelineSentiment"
            title="Sentiment Timeline"
            config={widgetConfigs.timelineSentiment}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('timelineSentiment', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
            wide
          >
            {(() => {
              const data = getFilteredTranscript('timelineSentiment')
              return (
                <TimelineChartJS
                  messages={data}
                  config={widgetConfigs.timelineSentiment}
                />
              )
            })()}
          </CustomizableWidget>

          {/* Toxicity Timeline */}
          <CustomizableWidget
            widgetId="timelineToxicity"
            title="Toxicity Timeline"
            config={widgetConfigs.timelineToxicity}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('timelineToxicity', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
            wide
          >
            {(() => {
              const data = getFilteredTranscript('timelineToxicity')
              return (
                <TimelineChartJS
                  messages={data}
                  config={widgetConfigs.timelineToxicity}
                />
              )
            })()}
          </CustomizableWidget>

          {/* Toxicity Gauge */}
          <CustomizableWidget
            widgetId="toxicityGauge"
            title="Toxicity Level"
            config={widgetConfigs.toxicityGauge}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('toxicityGauge', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
          >
            {(() => {
              const data = getFilteredTranscript('toxicityGauge')
              const stats = calculateStats(data)
              return (
                <ToxicityGaugeChartJS
                  score={stats.toxicity.average_toxicity_score}
                  config={widgetConfigs.toxicityGauge}
                />
              )
            })()}
          </CustomizableWidget>

          {/* Message Stream */}
          <CustomizableWidget
            widgetId="messageStream"
            title="Message Stream"
            config={widgetConfigs.messageStream}
            participants={participants}
            onConfigChange={(updates) => updateWidgetConfig('messageStream', updates)}
            openSettings={openSettings}
            setOpenSettings={setOpenSettings}
            wide
          >
            {(() => {
              const data = getFilteredTranscript('messageStream')
              return (
                <MessageStream
                  messages={data.slice(0, widgetConfigs.messageStream.limit)}
                  config={widgetConfigs.messageStream}
                />
              )
            })()}
          </CustomizableWidget>
        </div>
      )}
    </div>
  )
}

// ============================================
// CHART COMPONENTS
// ============================================

function SentimentDistributionChartJS({ data, config }) {
  /**
   * Horizontal bar chart showing sentiment distribution.
   * Uses Chart.js Bar component with stacked bars.
   */
  if (!data) return <div style={styles.emptyState}>No data</div>

  const total = (data.positive || 0) + (data.neutral || 0) + (data.negative || 0)
  if (total === 0) return <div style={styles.emptyState}>No data</div>

  const chartData = {
    labels: ['Sentiment Distribution'],
    datasets: [
      {
        label: 'Positive',
        data: [data.positive || 0],
        backgroundColor: '#34C759',
        borderRadius: 8,
      },
      {
        label: 'Neutral',
        data: [data.neutral || 0],
        backgroundColor: '#FFCC00',
        borderRadius: 8,
      },
      {
        label: 'Negative',
        data: [data.negative || 0],
        backgroundColor: '#FF3B30',
        borderRadius: 8,
      }
    ]
  }

  const options = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: config.showLabels,
        position: 'bottom',
        labels: {
          color: '#8e8e93',
          padding: 15,
          font: { size: 12 }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(28, 28, 30, 0.95)',
        titleColor: '#fff',
        bodyColor: '#d1d1d6',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        padding: 12,
        displayColors: true,
        callbacks: {
          label: (context) => {
            const value = context.parsed.x
            const percentage = ((value / total) * 100).toFixed(0)
            return `${context.dataset.label}: ${value} (${percentage}%)`
          }
        }
      }
    },
    scales: {
      x: {
        stacked: true,
        grid: {
          color: 'rgba(255, 255, 255, 0.05)',
          drawBorder: false
        },
        ticks: {
          color: '#8e8e93',
          font: { size: 11 }
        }
      },
      y: {
        stacked: true,
        display: false
      }
    },
    animation: {
      duration: config.animated ? 500 : 0
    }
  }

  return (
    <div style={{ height: '150px' }}>
      <Bar data={chartData} options={options} />
    </div>
  )
}

function TimelineChartJS({ messages, config }) {
  /**
   * Line chart showing sentiment or toxicity over time.
   * 
   * EDUCATIONAL NOTE:
   * X-axis shows message timestamps (formatted as MM:SS).
   * Y-axis shows sentiment/toxicity score (0-1).
   * Area fill can be enabled for better visualization.
   */
  if (!messages || messages.length === 0) {
    return <div style={styles.emptyState}>No data</div>
  }

  // Helper: Format timestamp HH:MM:SS.mmm → MM:SS
  const formatTime = (timestamp) => {
    const parts = timestamp.split(':')
    const minutes = parseInt(parts[1])
    const seconds = parseInt(parts[2].split('.')[0])
    return `${minutes}:${seconds.toString().padStart(2, '0')}`
  }

  // Prepare data points
  const dataPoints = messages.map((msg, idx) => {
    const score = config.metric === 'sentiment' 
      ? msg.sentiment.score 
      : msg.toxicity.toxicity_score
    
    return {
      x: idx,
      y: score,
      timestamp: msg.from,
      formattedTime: formatTime(msg.from),
      nickname: msg.nickname,
      text: msg.text
    }
  })

  // Create formatted labels (show every N messages to avoid overcrowding)
  const xLabels = dataPoints.map((dp, idx) => {
    const step = Math.max(1, Math.floor(messages.length / 10))
    
    if (idx === 0 || idx === messages.length - 1 || idx % step === 0) {
      return dp.formattedTime
    }
    return ''  // Empty label but point still exists
  })

  const chartColor = config.color || (config.metric === 'sentiment' ? '#00C7BE' : '#FF6B6B')

  const chartData = {
    labels: xLabels,
    datasets: [
      {
        label: config.metric === 'sentiment' ? 'Sentiment Score' : 'Toxicity Score',
        data: dataPoints.map(p => p.y),
        borderColor: chartColor,
        backgroundColor: config.showArea 
          ? chartColor + '30'
          : 'transparent',
        borderWidth: 3,
        fill: config.showArea,
        tension: 0.4,
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBackgroundColor: chartColor,
        pointBorderColor: '#1c1c1e',
        pointBorderWidth: 2,
        pointHoverBackgroundColor: chartColor,
        pointHoverBorderColor: '#fff'
      }
    ]
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: 'rgba(28, 28, 30, 0.95)',
        titleColor: '#fff',
        bodyColor: '#d1d1d6',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        padding: 12,
        displayColors: false,
        callbacks: {
          title: (context) => {
            const idx = context[0].dataIndex
            return `${dataPoints[idx].nickname} - ${dataPoints[idx].timestamp}`
          },
          label: (context) => {
            const score = context.parsed.y
            const metricName = config.metric === 'sentiment' ? 'Sentiment' : 'Toxicity'
            return `${metricName}: ${(score * 100).toFixed(0)}%`
          },
          afterLabel: (context) => {
            const idx = context.dataIndex
            const text = dataPoints[idx].text
            return `"${text.substring(0, 60)}${text.length > 60 ? '...' : ''}"`
          }
        }
      }
    },
    scales: {
      x: {
        grid: {
          display: config.showGrid,
          color: 'rgba(255, 255, 255, 0.05)',
          drawBorder: false
        },
        ticks: {
          display: true,
          color: '#8e8e93',
          font: { size: 10 },
          maxRotation: 0,
          minRotation: 0,
          autoSkip: false  // Show all non-empty labels
        }
      },
      y: {
        min: 0,
        max: 1,
        grid: {
          display: config.showGrid,
          color: 'rgba(255, 255, 255, 0.05)',
          drawBorder: false
        },
        ticks: {
          color: '#8e8e93',
          font: { size: 11 },
          callback: (value) => `${(value * 100).toFixed(0)}%`
        }
      }
    }
  }

  return (
    <div style={{ height: '300px' }}>
      <Line data={chartData} options={options} />
    </div>
  )
}

function ToxicityGaugeChartJS({ score, config }) {
  /**
   * Semi-circular gauge showing average toxicity level.
   * Uses Chart.js Doughnut chart with 180° rotation.
   */
  const safeScore = score ?? 0
  const percentage = (safeScore * 100).toFixed(0)
  
  // Determine color and label based on score
  const getColor = () => {
    if (safeScore < 0.3) return '#34C759'
    if (safeScore < 0.6) return '#FFCC00'
    return '#FF3B30'
  }

  const getLabel = () => {
    if (safeScore < 0.3) return 'LOW'
    if (safeScore < 0.6) return 'MEDIUM'
    return 'HIGH'
  }

  const color = getColor()
  const label = getLabel()

  const chartData = {
    datasets: [{
      data: [safeScore * 100, (1 - safeScore) * 100],
      backgroundColor: [color, 'rgba(255, 255, 255, 0.05)'],
      borderWidth: 0,
      circumference: 180,  // Half circle
      rotation: 270,       // Start from bottom
    }]
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '75%',
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        enabled: false
      }
    }
  }

  return (
    <div style={styles.gaugeContainer}>
      <div style={{ height: '180px', position: 'relative' }}>
        <Doughnut data={chartData} options={options} />
        <div style={{
          position: 'absolute',
          top: '55%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          textAlign: 'center'
        }}>
          <div style={{ ...styles.gaugeValue, color: color }}>
            {percentage}%
          </div>
          <div style={styles.gaugeLabel}>{label}</div>
        </div>
      </div>
      
      {config.showDetails && (
        <div style={styles.gaugeDetails}>
          <div style={styles.detailItem}>
            <span style={styles.detailLabel}>Toxicity Score</span>
            <span style={styles.detailValue}>{safeScore.toFixed(3)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================
// MESSAGE STREAM
// ============================================

function MessageStream({ messages, config }) {
  /**
   * Scrollable list of messages with sentiment and toxicity badges.
   */
  if (!messages || messages.length === 0) {
    return <div style={styles.emptyState}>No messages</div>
  }

  return (
    <div style={styles.messageStreamContainer}>
      {messages.map((msg) => (
        <MessageBubble key={msg.uid} message={msg} config={config} />
      ))}
    </div>
  )
}

function MessageBubble({ message, config }) {
  /**
   * Single message bubble with color-coded badges for sentiment and toxicity.
   */
  const getSentimentColor = (label) => {
    const colors = {
      positive: '#34C759',
      neutral: '#FFCC00',
      negative: '#FF3B30'
    }
    return colors[label] || '#8e8e93'
  }

  const getToxicityBadge = (toxicity) => {
    const colors = {
      low: '#34C759',
      medium: '#FF9500',
      high: '#FF3B30'
    }
    
    return {
      text: toxicity.severity.toUpperCase(),
      color: colors[toxicity.severity] || '#8e8e93'
    }
  }

  const badge = getToxicityBadge(message.toxicity)

  return (
    <div style={styles.messageBubble}>
      <div style={styles.bubbleHeader}>
        <span style={styles.bubbleAuthor}>{message.nickname}</span>
        <div style={styles.bubbleBadges}>
          <span
            style={{
              ...styles.sentimentBadge,
              backgroundColor: getSentimentColor(message.sentiment.label)
            }}
          >
            {(message.sentiment.score * 100).toFixed(0)}%
          </span>
          <span
            style={{
              ...styles.toxicBadge,
              backgroundColor: badge.color
            }}
          >
            {badge.text}
          </span>
        </div>
      </div>
      <p style={styles.bubbleText}>{message.text}</p>
      {config.showTimestamps && (
        <span style={styles.bubbleTime}>{message.from}</span>
      )}
    </div>
  )
}

// ============================================
// CUSTOMIZABLE WIDGET WRAPPER
// ============================================

function CustomizableWidget({
  widgetId,
  title,
  children,
  config,
  participants,
  onConfigChange,
  openSettings,
  setOpenSettings,
  wide
}) {
  /**
   * Reusable widget wrapper with settings panel.
   * Each widget can be customized independently.
   */
  const isOpen = openSettings === widgetId

  const toggleSettings = () => {
    setOpenSettings(isOpen ? null : widgetId)
  }

  return (
    <div style={{ ...styles.iosWidget, ...(wide && styles.wideWidget) }}>
      <div style={styles.widgetHeader}>
        <span style={styles.widgetTitle}>{title}</span>
        <div style={styles.headerActions}>
          <div style={{ ...styles.widgetDot, backgroundColor: config.color }} />
          <button onClick={toggleSettings} style={styles.settingsButton}>
            {isOpen ? '✕' : '⋯'}
          </button>
        </div>
      </div>

      {isOpen && (
        <WidgetSettings
          config={config}
          participants={participants}
          onConfigChange={onConfigChange}
        />
      )}

      <div style={styles.widgetContent}>{children}</div>
    </div>
  )
}

// ============================================
// WIDGET SETTINGS PANEL
// ============================================

function WidgetSettings({ config, participants, onConfigChange }) {
  /**
   * Settings panel for customizing widget behavior.
   * Each widget has different available settings.
   */
  return (
    <div style={styles.settingsPanel}>
      {/* Participant filter (available for all widgets) */}
      <div style={styles.settingRow}>
        <span style={styles.settingLabel}>Filter</span>
        <select
          value={config.participantFilter || ''}
          onChange={(e) =>
            onConfigChange({ participantFilter: e.target.value || null })
          }
          style={styles.settingSelect}
        >
          <option value="">All</option>
          {participants.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      {/* Show Details toggle */}
      {config.showDetails !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Show Details</span>
          <label style={styles.toggleSwitch}>
            <input
              type="checkbox"
              checked={config.showDetails}
              onChange={(e) =>
                onConfigChange({ showDetails: e.target.checked })
              }
              style={styles.toggleInput}
            />
            <span
              style={{
                ...styles.toggleSlider,
                backgroundColor: config.showDetails ? config.color : '#3a3a3c'
              }}
            />
          </label>
        </div>
      )}

      {/* Show Labels toggle */}
      {config.showLabels !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Show Labels</span>
          <label style={styles.toggleSwitch}>
            <input
              type="checkbox"
              checked={config.showLabels}
              onChange={(e) =>
                onConfigChange({ showLabels: e.target.checked })
              }
              style={styles.toggleInput}
            />
            <span
              style={{
                ...styles.toggleSlider,
                backgroundColor: config.showLabels ? config.color : '#3a3a3c'
              }}
            />
          </label>
        </div>
      )}

      {/* Animated toggle */}
      {config.animated !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Animated</span>
          <label style={styles.toggleSwitch}>
            <input
              type="checkbox"
              checked={config.animated}
              onChange={(e) =>
                onConfigChange({ animated: e.target.checked })
              }
              style={styles.toggleInput}
            />
            <span
              style={{
                ...styles.toggleSlider,
                backgroundColor: config.animated ? config.color : '#3a3a3c'
              }}
            />
          </label>
        </div>
      )}

      {/* Show Timestamps toggle */}
      {config.showTimestamps !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Timestamps</span>
          <label style={styles.toggleSwitch}>
            <input
              type="checkbox"
              checked={config.showTimestamps}
              onChange={(e) =>
                onConfigChange({ showTimestamps: e.target.checked })
              }
              style={styles.toggleInput}
            />
            <span
              style={{
                ...styles.toggleSlider,
                backgroundColor: config.showTimestamps ? config.color : '#3a3a3c'
              }}
            />
          </label>
        </div>
      )}

      {/* Metric selector (sentiment/toxicity) */}
      {config.metric !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Metric</span>
          <select
            value={config.metric}
            onChange={(e) => onConfigChange({ metric: e.target.value })}
            style={styles.settingSelect}
          >
            <option value="sentiment">Sentiment</option>
            <option value="toxicity">Toxicity</option>
          </select>
        </div>
      )}

      {/* Show Grid toggle */}
      {config.showGrid !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Show Grid</span>
          <label style={styles.toggleSwitch}>
            <input
              type="checkbox"
              checked={config.showGrid}
              onChange={(e) =>
                onConfigChange({ showGrid: e.target.checked })
              }
              style={styles.toggleInput}
            />
            <span
              style={{
                ...styles.toggleSlider,
                backgroundColor: config.showGrid ? config.color : '#3a3a3c'
              }}
            />
          </label>
        </div>
      )}

      {/* Show Area toggle */}
      {config.showArea !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Show Area</span>
          <label style={styles.toggleSwitch}>
            <input
              type="checkbox"
              checked={config.showArea}
              onChange={(e) =>
                onConfigChange({ showArea: e.target.checked })
              }
              style={styles.toggleInput}
            />
            <span
              style={{
                ...styles.toggleSlider,
                backgroundColor: config.showArea ? config.color : '#3a3a3c'
              }}
            />
          </label>
        </div>
      )}

      {/* Message limit input */}
      {config.limit !== undefined && (
        <div style={styles.settingRow}>
          <span style={styles.settingLabel}>Message Limit</span>
          <input
            type="number"
            min="5"
            max="100"
            value={config.limit}
            onChange={(e) => {
              const newLimit = parseInt(e.target.value)
              if (!isNaN(newLimit) && newLimit >= 5 && newLimit <= 100) {
                onConfigChange({ limit: newLimit })
              }
            }}
            style={styles.numberInput}
          />
        </div>
      )}
    </div>
  )
}

// ============================================
// STYLES (iOS-inspired dark theme)
// ============================================

const styles = {
  appContainer: {
    minHeight: '100vh',
    backgroundColor: '#1c1c1e',
    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif',
    color: '#fff'
  },
  header: {
    position: 'sticky',
    top: 0,
    zIndex: 100,
    backgroundColor: 'rgba(28, 28, 30, 0.85)',
    backdropFilter: 'saturate(180%) blur(20px)',
    WebkitBackdropFilter: 'saturate(180%) blur(20px)',
    borderBottom: '0.5px solid rgba(255, 255, 255, 0.1)',
    padding: '1.25rem 0',
    boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)'
  },
  headerContent: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '0 2rem'
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '1.25rem'
  },
  logoCircle: {
    width: '56px',
    height: '56px',
    borderRadius: '14px',
    background: 'linear-gradient(135deg, #FF3B30 0%, #FF9500 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '1.4rem',
    fontWeight: '700',
    color: '#fff',
    boxShadow: '0 8px 24px rgba(255, 59, 48, 0.5)'
  },
  title: {
    margin: 0,
    fontSize: '1.5rem',
    fontWeight: '700',
    color: '#fff',
    letterSpacing: '-0.02em'
  },
  subtitle: {
    margin: 0,
    fontSize: '0.9rem',
    color: '#8e8e93',
    fontWeight: '500'
  },
  errorBanner: {
    padding: '1rem 2rem',
    margin: '1rem 2rem',
    backgroundColor: '#3a3a3c',
    borderRadius: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    fontSize: '0.9rem',
    color: '#FF3B30'
  },
  errorIcon: {
    width: '24px',
    height: '24px',
    borderRadius: '12px',
    backgroundColor: '#FF3B30',
    color: 'white',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: '700'
  },
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '60vh',
    gap: '1.5rem'
  },
  spinner: {
    width: '50px',
    height: '50px',
    border: '4px solid #3a3a3c',
    borderTop: '4px solid #007AFF',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite'
  },
  loadingText: {
    fontSize: '0.95rem',
    fontWeight: '500',
    color: '#8e8e93'
  },
  widgetGrid: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '2.5rem 2rem',
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '1.5rem'
  },
  iosWidget: {
    borderRadius: '24px',
    padding: '1.75rem',
    backgroundColor: 'rgba(44, 44, 46, 0.6)',
    backdropFilter: 'blur(20px)',
    WebkitBackdropFilter: 'blur(20px)',
    border: '0.5px solid rgba(255, 255, 255, 0.08)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), 0 2px 8px rgba(0, 0, 0, 0.3)',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
  },
  wideWidget: {
    gridColumn: 'span 2'
  },
  widgetHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '1.5rem',
    paddingBottom: '0.75rem',
    borderBottom: '0.5px solid rgba(255, 255, 255, 0.06)'
  },
  widgetTitle: {
    fontSize: '1.05rem',
    fontWeight: '600',
    color: '#fff',
    letterSpacing: '-0.01em'
  },
  headerActions: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.875rem'
  },
  widgetDot: {
    width: '10px',
    height: '10px',
    borderRadius: '5px',
    boxShadow: '0 0 12px currentColor, 0 0 4px currentColor'
  },
  settingsButton: {
    width: '34px',
    height: '34px',
    borderRadius: '10px',
    border: 'none',
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    color: '#fff',
    fontSize: '1.3rem',
    fontWeight: '600',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)'
  },
  widgetContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1.25rem'
  },
  settingsPanel: {
    marginBottom: '1.5rem',
    padding: '1.25rem',
    borderRadius: '16px',
    backgroundColor: 'rgba(28, 28, 30, 0.8)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    border: '0.5px solid rgba(255, 255, 255, 0.08)',
    display: 'flex',
    flexDirection: 'column',
    gap: '1rem',
    animation: 'slideDown 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    boxShadow: '0 4px 16px rgba(0, 0, 0, 0.3)'
  },
  settingRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: '1rem',
    padding: '0.5rem 0'
  },
  settingLabel: {
    fontSize: '0.9rem',
    fontWeight: '500',
    color: '#8e8e93',
    letterSpacing: '-0.01em'
  },
  settingSelect: {
    padding: '0.625rem 1rem',
    fontSize: '0.875rem',
    borderRadius: '10px',
    border: '0.5px solid rgba(255, 255, 255, 0.1)',
    backgroundColor: 'rgba(44, 44, 46, 0.6)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    color: '#fff',
    outline: 'none',
    fontWeight: '500',
    cursor: 'pointer',
    minWidth: '140px',
    transition: 'all 0.2s ease'
  },
  numberInput: {
    padding: '0.625rem 1rem',
    fontSize: '0.875rem',
    borderRadius: '10px',
    border: '0.5px solid rgba(255, 255, 255, 0.1)',
    backgroundColor: 'rgba(44, 44, 46, 0.6)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    color: '#fff',
    outline: 'none',
    fontWeight: '500',
    width: '90px',
    textAlign: 'center',
    transition: 'all 0.2s ease'
  },
  toggleSwitch: {
    position: 'relative',
    display: 'inline-block',
    width: '50px',
    height: '28px',
    cursor: 'pointer'
  },
  toggleInput: {
    opacity: 0,
    width: 0,
    height: 0
  },
  toggleSlider: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: '14px',
    transition: 'background-color 0.3s ease',
    display: 'flex',
    alignItems: 'center',
    padding: '0 2px'
  },
  kpiValue: {
    fontSize: '3.5rem',
    fontWeight: '700',
    color: '#fff',
    textAlign: 'center',
    lineHeight: '1',
    letterSpacing: '-0.03em',
    textShadow: '0 2px 8px rgba(0, 0, 0, 0.3)'
  },
  kpiLabel: {
    fontSize: '0.9rem',
    fontWeight: '500',
    color: '#8e8e93',
    textAlign: 'center',
    letterSpacing: '-0.01em',
    marginTop: '0.5rem'
  },
  emptyState: {
    textAlign: 'center',
    padding: '2rem',
    color: '#8e8e93',
    fontSize: '0.9rem',
    fontWeight: '500'
  },
  gaugeContainer: {
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    gap: '1.25rem',
    padding: '1.5rem 0'
  },
  gaugeValue: {
    fontSize: '2.75rem',
    fontWeight: '700',
    letterSpacing: '-0.02em',
    textShadow: '0 2px 8px rgba(0, 0, 0, 0.3)'
  },
  gaugeLabel: {
    fontSize: '0.8rem',
    fontWeight: '600',
    color: '#8e8e93',
    letterSpacing: '1.5px',
    marginTop: '0.375rem',
    textTransform: 'uppercase'
  },
  gaugeDetails: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.625rem'
  },
  detailItem: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '0.75rem 1.25rem',
    borderRadius: '12px',
    backgroundColor: 'rgba(28, 28, 30, 0.6)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    border: '0.5px solid rgba(255, 255, 255, 0.06)'
  },
  detailLabel: {
    fontSize: '0.85rem',
    fontWeight: '500',
    color: '#8e8e93',
    letterSpacing: '-0.01em'
  },
  detailValue: {
    fontSize: '0.95rem',
    fontWeight: '600',
    color: '#fff',
    letterSpacing: '-0.01em'
  },
  messageStreamContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '0.875rem',
    maxHeight: '600px',
    overflowY: 'auto',
    paddingRight: '0.5rem'
  },
  messageBubble: {
    padding: '1rem 1.25rem',
    borderRadius: '16px',
    backgroundColor: 'rgba(28, 28, 30, 0.6)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    border: '0.5px solid rgba(255, 255, 255, 0.06)',
    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)'
  },
  bubbleHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: '0.625rem'
  },
  bubbleAuthor: {
    fontSize: '0.9rem',
    fontWeight: '600',
    color: '#fff',
    letterSpacing: '-0.01em'
  },
  bubbleBadges: {
    display: 'flex',
    gap: '0.5rem'
  },
  sentimentBadge: {
    fontSize: '0.75rem',
    fontWeight: '700',
    color: '#000',
    padding: '0.3rem 0.6rem',
    borderRadius: '8px',
    letterSpacing: '0.02em'
  },
  toxicBadge: {
    fontSize: '0.7rem',
    fontWeight: '700',
    color: '#fff',
    padding: '0.3rem 0.6rem',
    borderRadius: '8px',
    letterSpacing: '0.5px',
    textTransform: 'uppercase'
  },
  bubbleText: {
    margin: 0,
    fontSize: '0.9rem',
    lineHeight: '1.6',
    color: '#d1d1d6',
    letterSpacing: '-0.01em'
  },
  bubbleTime: {
    display: 'block',
    marginTop: '0.625rem',
    fontSize: '0.75rem',
    fontWeight: '500',
    color: '#636366',
    letterSpacing: '0.02em'
  }
}

// CSS animations (injected into DOM)
const styleSheet = document.createElement('style')
styleSheet.textContent = `
@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Toggle switch pseudo-elements */
input[type="checkbox"]:checked + span::after {
  content: '';
  position: absolute;
  width: 24px;
  height: 24px;
  background-color: white;
  border-radius: 12px;
  right: 2px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

input[type="checkbox"]:not(:checked) + span::after {
  content: '';
  position: absolute;
  width: 24px;
  height: 24px;
  background-color: white;
  border-radius: 12px;
  left: 2px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
`
document.head.appendChild(styleSheet)

export default App