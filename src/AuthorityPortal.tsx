import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  Check,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  FileClock,
  MapPin,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import { api } from './api'
import type { AuditEvent, AuthorityOutcome, Flag, MonthlyAuthorityMetrics } from './types'

type AuthorityView = 'inbox' | 'monthly'

const statusNames: Record<string, string> = {
  authority_review: 'Awaiting review',
  field_visit: 'Field visit requested',
  action_taken: 'Action taken',
  not_illegal: 'Not illegal',
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value))
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function formatMonth(value: string) {
  const [year, month] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric' }).format(new Date(year, month - 1, 1))
}

function ReviewMap({ flag }: { flag: Flag }) {
  return (
    <MapContainer key={flag.id} center={[flag.latitude, flag.longitude]} zoom={16} scrollWheelZoom={false} className="location-map authority-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <CircleMarker center={[flag.latitude, flag.longitude]} radius={10} pathOptions={{ color: '#9b4d34', weight: 3, fillColor: '#dc7955', fillOpacity: 0.9 }}>
        <Popup>{flag.reference} · {flag.zone_name}</Popup>
      </CircleMarker>
    </MapContainer>
  )
}

function EventRow({ event }: { event: AuditEvent }) {
  return (
    <article className="authority-event">
      <span className={event.actor_role === 'authority' ? 'event-dot authority-dot' : 'event-dot analyst-dot'}><Activity size={12} /></span>
      <div className="authority-event-copy">
        <div className="authority-event-top"><strong>{event.summary}</strong><time>{formatTime(event.created_at)}</time></div>
        <span className="event-byline">{event.actor} <i>·</i> {event.actor_role === 'authority' ? 'Authority reviewer' : event.actor_role === 'analyst' ? 'Analyst' : 'System'}</span>
        {event.note && <p>{event.note}</p>}
      </div>
    </article>
  )
}

function AuthorityPortal({ actor, error, onError }: { actor: string; error: string; onError: (message: string) => void }) {
  const [view, setView] = useState<AuthorityView>('inbox')
  const [flags, setFlags] = useState<Flag[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [metrics, setMetrics] = useState<MonthlyAuthorityMetrics | null>(null)
  const [outcome, setOutcome] = useState<AuthorityOutcome | null>(null)
  const [comment, setComment] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [success, setSuccess] = useState('')

  const selected = flags.find((flag) => flag.id === selectedId) ?? null

  async function loadFlags() {
    setRefreshing(true)
    try {
      const result = await api.listAuthorityFlags(actor)
      setFlags(result)
      setSelectedId((current) => current && result.some((flag) => flag.id === current) ? current : result[0]?.id ?? null)
      onError('')
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not load referred flags.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { void loadFlags() }, [actor])

  useEffect(() => {
    if (!selectedId) {
      setEvents([])
      return
    }
    api.listFlagAudit(selectedId, 'authority').then(setEvents).catch((error) => onError(error instanceof Error ? error.message : 'Could not load the case history.'))
  }, [selectedId, flags, actor])

  useEffect(() => {
    if (view !== 'monthly') return
    api.authorityMonthlyMetrics(actor, 12).then(setMetrics).catch((error) => onError(error instanceof Error ? error.message : 'Could not load monthly totals.'))
  }, [view, actor, flags])

  useEffect(() => {
    if (!success) return
    const timer = window.setTimeout(() => setSuccess(''), 3500)
    return () => window.clearTimeout(timer)
  }, [success])

  const visibleFlags = useMemo(() => flags.filter((flag) => `${flag.reference} ${flag.zone_name} ${flag.address} ${flag.signal_label}`.toLowerCase().includes(query.toLowerCase())), [flags, query])
  const awaiting = flags.filter((flag) => ['authority_review', 'field_visit'].includes(flag.status)).length
  const decided = flags.filter((flag) => ['action_taken', 'not_illegal'].includes(flag.status)).length
  const actionCount = flags.filter((flag) => flag.status === 'action_taken').length

  async function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || !outcome || comment.trim().length < 3) return
    setSaving(true)
    try {
      await api.authorityDecision(selected.id, outcome, comment.trim(), actor)
      setOutcome(null)
      setComment('')
      await loadFlags()
      setEvents(await api.listFlagAudit(selected.id, 'authority'))
      setSuccess(outcome === 'action_taken' ? 'Authority action recorded in the case history.' : 'Marked not illegal with comment recorded.')
      onError('')
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Could not submit this authority decision.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-content authority-content">
      <div className="page-heading">
        <div><div className="eyebrow"><span /> NAGPUR MUNICIPAL CORPORATION · AUTHORITY DESK</div><h1>Authority validation</h1><p>Review referred screening flags, record a decision, and retain the responsible reviewer in the case history.</p></div>
        <button className="quiet-button" onClick={() => void loadFlags()} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'spinning' : ''} /> Refresh</button>
      </div>

      <div className="demo-notice authority-demo"><CircleAlert size={15} /><span><strong>Authority portal · demo mode.</strong> Decisions are illustrative. Production access must use verified organization sign-in and assigned authority accounts.</span></div>

      {error && <div className="error-banner"><CircleAlert size={16} /><span>{error}</span><button onClick={() => onError('')} aria-label="Dismiss error"><X size={16} /></button></div>}
      {success && <div className="authority-success"><Check size={15} />{success}</div>}

      <section className="metric-strip authority-metrics" aria-label="Authority summary">
        <div className="metric-cell"><span className="metric-icon metric-amber"><Clock3 size={17} /></span><div><span>AWAITING DECISION</span><strong>{awaiting.toString().padStart(2, '0')}</strong></div><small>referred flags</small></div>
        <div className="metric-cell"><span className="metric-icon metric-blue"><ShieldCheck size={17} /></span><div><span>REVIEWED</span><strong>{decided.toString().padStart(2, '0')}</strong></div><small>final decisions</small></div>
        <div className="metric-cell metric-last"><span className="metric-icon metric-green"><ClipboardCheck size={17} /></span><div><span>ACTION TAKEN</span><strong>{actionCount.toString().padStart(2, '0')}</strong></div><small>last 12 months</small></div>
      </section>

      <div className="authority-tabs" role="tablist" aria-label="Authority views">
        <button className={view === 'inbox' ? 'authority-tab selected' : 'authority-tab'} onClick={() => setView('inbox')}><ClipboardCheck size={15} /> Referred flags <span>{flags.length}</span></button>
        <button className={view === 'monthly' ? 'authority-tab selected' : 'authority-tab'} onClick={() => setView('monthly')}><ArrowDownRight size={15} /> Monthly actions</button>
      </div>

      {view === 'inbox' ? (
        <div className="authority-workbench">
          <section className="authority-queue panel-shell">
            <div className="panel-heading"><div><span className="section-kicker">REFERRED BY ANALYSTS</span><h2>Authority queue <span>{flags.length}</span></h2></div><span className="authority-lock"><ShieldCheck size={13} /> AUTHORITY</span></div>
            <div className="queue-search"><MapPin size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search flag, zone, or location" /></div>
            <div className="authority-flag-list">
              {loading ? <div className="empty-state">Loading referred flags…</div> : visibleFlags.length === 0 ? <div className="empty-state">No flags have been referred yet.</div> : visibleFlags.map((flag) => (
                <button key={flag.id} className={selectedId === flag.id ? 'authority-flag selected' : 'authority-flag'} onClick={() => { setSelectedId(flag.id); setOutcome(null); setComment('') }}>
                  <div className="authority-flag-top"><span className="flag-ref">{flag.reference}</span><span className={`authority-status authority-${flag.status}`}>{statusNames[flag.status] ?? flag.status}</span></div>
                  <strong>{flag.zone_name}</strong><span>{flag.signal_label} · {flag.area_hectares.toFixed(2)} ha</span>
                  <div className="authority-flag-bottom"><MapPin size={12} /> {flag.latitude.toFixed(4)}, {flag.longitude.toFixed(4)}<time>{formatDate(flag.updated_at)}</time></div>
                </button>
              ))}
            </div>
          </section>

          <section className="authority-case panel-shell">
            {selected ? <>
              <div className="authority-case-heading"><div className="authority-case-overline"><span>{selected.reference}</span><span className={`authority-status authority-${selected.status}`}>{statusNames[selected.status] ?? selected.status}</span></div><h2>{selected.signal_label}</h2><p>{selected.zone_name} · {selected.address}</p></div>
              <div className="authority-evidence-grid">
                <div className="authority-map-frame"><ReviewMap flag={selected} /></div>
                <div className="authority-facts"><div><span>COORDINATES</span><strong>{selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)}</strong></div><div><span>ESTIMATED AREA</span><strong>{selected.area_hectares.toFixed(2)} ha</strong></div><div><span>SCREENING SIGNAL</span><strong>{selected.signal_label} · index {selected.signal_index}</strong></div><div><span>SCENE PERIOD</span><strong>{formatDate(selected.epoch_t0)} <ChevronRight size={13} /> {formatDate(selected.epoch_t1)}</strong></div></div>
              </div>
              <div className="authority-summary"><span className="section-kicker">ANALYST EVIDENCE SUMMARY</span><p>{selected.evidence_summary}</p></div>

              {['authority_review', 'field_visit'].includes(selected.status) ? (
                <div className="decision-section">
                  <div className="decision-section-head"><div><span className="section-kicker">AUTHORITY DETERMINATION</span><h3>Record review outcome</h3></div><span className="required-note">Comment required</span></div>
                  {!outcome ? <div className="decision-options"><button className="take-action-option" onClick={() => setOutcome('action_taken')}><Check size={16} /><span><strong>Take action</strong><small>Record the action taken on this flag</small></span><ChevronRight size={15} /></button><button className="not-illegal-option" onClick={() => setOutcome('not_illegal')}><X size={16} /><span><strong>Not illegal</strong><small>Close as authorized or not a violation</small></span><ChevronRight size={15} /></button></div> : (
                    <form className="decision-comment-form" onSubmit={submitDecision}>
                      <div className="decision-form-title"><strong>{outcome === 'action_taken' ? 'Action taken' : 'Not illegal'}</strong><button type="button" className="text-button" onClick={() => setOutcome(null)}>Change outcome</button></div>
                      <label htmlFor="authority-comment">REVIEW COMMENT <span>*</span></label>
                      <textarea id="authority-comment" autoFocus minLength={3} maxLength={2000} required value={comment} onChange={(event) => setComment(event.target.value)} placeholder={outcome === 'action_taken' ? 'Describe the enforcement or follow-up action and reference…' : 'Explain why the location is not illegal; cite the permit or validation…'} rows={3} />
                      <div className="decision-form-actions"><span>{comment.trim().length}/2000 · saved with reviewer identity and timestamp</span><button className="primary-button" disabled={saving || comment.trim().length < 3} type="submit">{saving ? 'Recording…' : 'Submit authority decision'} <ArrowRight size={14} /></button></div>
                    </form>
                  )}
                </div>
              ) : (
                <div className={selected.status === 'action_taken' ? 'decision-result result-action' : 'decision-result result-not-illegal'}><ShieldCheck size={17} /><div><span>AUTHORITY OUTCOME</span><strong>{selected.status === 'action_taken' ? 'Action taken' : 'Not illegal'}</strong><small>Final outcome is recorded below with reviewer name and comment.</small></div></div>
              )}

              <div className="authority-history"><div className="authority-history-heading"><div><span className="section-kicker">APPEND-ONLY CASE HISTORY</span><h3>Who did what</h3></div><span>{events.length} events</span></div>{events.map((event) => <EventRow key={event.id} event={event} />)}{events.length === 0 && <div className="empty-state">No events recorded on this flag yet.</div>}</div>
            </> : <div className="empty-state">Select a referred flag to inspect its evidence and history.</div>}
          </section>
        </div>
      ) : (
        <MonthlyActions metrics={metrics} />
      )}
    </div>
  )
}

export function MonthlyActions({ metrics }: { metrics: MonthlyAuthorityMetrics | null }) {
  if (!metrics) return <section className="panel-shell monthly-loading"><div className="empty-state">Loading monthly action totals…</div></section>
  if (metrics.corporations.length === 0) return <section className="panel-shell monthly-loading"><div className="empty-state">No corporation action totals available.</div></section>

  return <div className="monthly-corporations">{metrics.corporations.map((corporation) => {
    const totalAction = corporation.items.reduce((sum, item) => sum + item.action_taken, 0)
    const totalNotIllegal = corporation.items.reduce((sum, item) => sum + item.not_illegal, 0)
    const max = Math.max(1, ...corporation.items.map((item) => item.action_taken + item.not_illegal))
    return <section className="monthly-corporation panel-shell" key={corporation.corporation_name}>
      <div className="monthly-heading"><div><span className="section-kicker">AUTHORITY OUTCOME REGISTER</span><h2>{corporation.corporation_name}</h2><p>Monthly decisions recorded against referred flags</p></div><span className="monthly-period">LAST 12 MONTHS</span></div>
      <div className="monthly-summary"><div><span>ACTION TAKEN</span><strong>{totalAction}</strong></div><div><span>NOT ILLEGAL</span><strong>{totalNotIllegal}</strong></div><div><span>TOTAL DECISIONS</span><strong>{totalAction + totalNotIllegal}</strong></div></div>
      <div className="monthly-chart" aria-label={`Monthly authority decisions for ${corporation.corporation_name}`}>
        <div className="monthly-chart-legend"><span><i className="monthly-action-swatch" /> Action taken</span><span><i className="monthly-clear-swatch" /> Not illegal</span></div>
        {corporation.items.map((item) => <div className="month-row" key={item.month}><span className="month-label">{formatMonth(item.month)}</span><div className="month-track"><i className="month-action-bar" style={{ width: `${item.action_taken / max * 100}%` }} /><i className="month-clear-bar" style={{ width: `${item.not_illegal / max * 100}%` }} /></div><span className="month-count">{item.action_taken + item.not_illegal}</span><span className="month-detail">{item.action_taken} action · {item.not_illegal} cleared</span></div>)}
      </div>
      <div className="monthly-footnote"><FileClock size={14} /> Counts are based on authority decisions and timestamps in the append-only audit log.</div>
    </section>
  })}</div>
}

export default AuthorityPortal