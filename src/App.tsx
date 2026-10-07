import { useEffect, useState, type FormEvent } from 'react'
import {
  Activity,
  ArrowDownUp,
  ArrowRight,
  Bell,
  Check,
  CheckCheck,
  ChevronDown,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  FileClock,
  Filter,
  MapPin,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  X,
  XCircle,
} from 'lucide-react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import type { AuditEvent, Flag, FlagPriority, FlagStatus, MonthlyAuthorityMetrics } from './types'
import { api } from './api'
import AuthorityPortal, { MonthlyActions } from './AuthorityPortal'
import 'leaflet/dist/leaflet.css'
import './dashboard.css'

const statusLabels: Record<FlagStatus, string> = {
  new: 'New',
  triage: 'Analyst review',
  assigned: 'Assigned',
  authority_review: 'Authority review',
  field_visit: 'Field visit',
  confirmed: 'Confirmed',
  not_confirmed: 'Not confirmed',
  closed: 'Closed',
  action_taken: 'Action taken',
  not_illegal: 'Not illegal',
}

const statusFilters = [
  { label: 'All flags', value: 'all' },
  { label: 'Needs review', value: 'needs_review' },
  { label: 'With authority', value: 'authority' },
  { label: 'Decided', value: 'decided' },
]

const analystUsers = ['A. Kulkarni', 'R. Mehta', 'S. Deshmukh']
const authorityUsers = ['P. Rao', 'A. Wankhede', 'Municipal review desk']
const reviewers = [...analystUsers, ...authorityUsers]

function formatDate(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value))
}

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function StatusPill({ status }: { status: FlagStatus }) {
  return <span className={`status-pill status-${status}`}>{statusLabels[status]}</span>
}

function LocationMap({ flag }: { flag: Flag }) {
  return (
    <MapContainer key={`${flag.latitude}-${flag.longitude}`} center={[flag.latitude, flag.longitude]} zoom={16} scrollWheelZoom={false} className="location-map">
      <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <CircleMarker center={[flag.latitude, flag.longitude]} radius={10} pathOptions={{ color: '#a53e2c', weight: 3, fillColor: '#e77752', fillOpacity: 0.88 }}>
        <Popup>{flag.reference} · {flag.zone_name}</Popup>
      </CircleMarker>
    </MapContainer>
  )
}

function AuditLine({ event }: { event: AuditEvent }) {
  return (
    <article className="audit-entry">
      <span className={`audit-symbol audit-${event.action.toLowerCase()}`}>
        {event.action === 'FLAG_CREATED' ? <Plus size={13} /> : event.action === 'NOTE_ADDED' ? <MessageSquare size={13} /> : <Activity size={13} />}
      </span>
      <div className="audit-copy">
        <div className="audit-title-row"><strong>{event.summary}</strong><time>{formatTimestamp(event.created_at)}</time></div>
        <p>{event.actor}{event.note ? ` · ${event.note}` : ''}</p>
      </div>
    </article>
  )
}

function App() {
  const [activePortal, setActivePortal] = useState<'analyst' | 'authority'>('analyst')
  const [flags, setFlags] = useState<Flag[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [globalAudit, setGlobalAudit] = useState<AuditEvent[]>([])
  const [corporationMetrics, setCorporationMetrics] = useState<MonthlyAuthorityMetrics | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [activeView, setActiveView] = useState<'queue' | 'audit' | 'monthly'>('queue')
  const [actor, setActor] = useState('R. Mehta')
  const [showCreate, setShowCreate] = useState(false)
  const [note, setNote] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const actorOptions = activePortal === 'analyst' ? analystUsers : authorityUsers

  const selectedFlag = flags.find((flag) => flag.id === selectedId) ?? null

  async function loadFlags() {
    setRefreshing(true)
    try {
      const result = await api.listFlags()
      setFlags(result)
      setSelectedId((current) => current && result.some((flag) => flag.id === current) ? current : result[0]?.id ?? null)
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not connect to the case service.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { void loadFlags() }, [])
  useEffect(() => {
    if (!selectedId) { setAudit([]); return }
    api.listFlagAudit(selectedId).then(setAudit).catch(() => setAudit([]))
  }, [selectedId, flags])
  useEffect(() => {
    if (activePortal === 'analyst' && activeView === 'audit') api.listAudit().then(setGlobalAudit).catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load audit trail.'))
  }, [activePortal, activeView, flags])
  useEffect(() => {
    if (activePortal === 'analyst' && activeView === 'monthly') api.corporationMonthlyMetrics(actor, 12).then(setCorporationMetrics).catch((caught) => setError(caught instanceof Error ? caught.message : 'Could not load monthly corporation totals.'))
  }, [activePortal, activeView, actor])
  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(''), 3000)
    return () => window.clearTimeout(timeout)
  }, [toast])

  const visibleFlags = flags.filter((flag) => {
    const textMatch = `${flag.reference} ${flag.zone_name} ${flag.signal_label} ${flag.address}`.toLowerCase().includes(query.toLowerCase())
    const statusMatch = statusFilter === 'all'
      || (statusFilter === 'needs_review' && ['new', 'triage'].includes(flag.status))
      || (statusFilter === 'authority' && ['assigned', 'authority_review', 'field_visit'].includes(flag.status))
      || (statusFilter === 'decided' && ['confirmed', 'not_confirmed', 'closed', 'action_taken', 'not_illegal'].includes(flag.status))
    return textMatch && statusMatch
  })
  const needsReview = flags.filter((flag) => ['new', 'triage'].includes(flag.status)).length
  const withAuthority = flags.filter((flag) => ['assigned', 'authority_review', 'field_visit'].includes(flag.status)).length
  const highPriority = flags.filter((flag) => flag.priority === 'high' && !['confirmed', 'not_confirmed', 'closed', 'action_taken', 'not_illegal'].includes(flag.status)).length

  async function updateFlag(changes: { status?: FlagStatus; assignee?: string; priority?: FlagPriority }, summary: string) {
    if (!selectedFlag) return
    try {
      await api.updateFlag(selectedFlag.id, changes, actor)
      await loadFlags()
      setToast(summary)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not update this flag.')
    }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedFlag || !note.trim()) return
    try {
      await api.addNote(selectedFlag.id, note.trim(), actor)
      setNote('')
      setAudit(await api.listFlagAudit(selectedFlag.id))
      setToast('Review note added to audit trail')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save the note.')
    }
  }

  async function createFlag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const payload = {
      zone_name: String(form.get('zone_name')),
      address: String(form.get('address')),
      signal_label: String(form.get('signal_label')),
      latitude: Number(form.get('latitude')),
      longitude: Number(form.get('longitude')),
      area_hectares: Number(form.get('area_hectares')),
      signal_index: Number(form.get('signal_index')),
      epoch_t0: String(form.get('epoch_t0')),
      epoch_t1: String(form.get('epoch_t1')),
      evidence_summary: String(form.get('evidence_summary')),
    }
    try {
      const created = await api.createFlag(payload, actor)
      await loadFlags()
      setSelectedId(created.id)
      setActiveView('queue')
      setShowCreate(false)
      setToast(`${created.reference} added to the review queue`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create flag.')
    }
  }

  return (
    <div className="app-shell">
      <aside className="side-rail">
        <div className="brand-lockup"><div className="brand-mark"><ShieldCheck size={21} /></div><div><strong>Abhilekh</strong><span>FIELD REVIEW SYSTEM</span></div></div>
        <div className="rail-label">WORKSPACE</div>
        {activePortal === 'analyst' && <nav className="rail-nav" aria-label="Analyst navigation">
          <button className={activeView === 'queue' ? 'rail-link is-active' : 'rail-link'} onClick={() => setActiveView('queue')}><ClipboardCheck size={17} /><span>Flag queue</span><b>{flags.length}</b></button>
          <button className={activeView === 'audit' ? 'rail-link is-active' : 'rail-link'} onClick={() => setActiveView('audit')}><FileClock size={17} /><span>Audit trail</span></button>
          <button className={activeView === 'monthly' ? 'rail-link is-active' : 'rail-link'} onClick={() => setActiveView('monthly')}><Activity size={17} /><span>Monthly actions</span></button>
        </nav>}
        {activePortal === 'authority' && <div className="authority-rail-label"><ShieldCheck size={15} /> AUTHORITY REVIEW</div>}
        <div className="rail-context"><div className="context-overline"><span className="live-dot" /> PILOT ENVIRONMENT</div><strong>Nagpur Municipal<br />Corporation</strong><span>{activePortal === 'analyst' ? 'Screening operations' : 'Authority validation desk'}</span></div>
        <div className="rail-footer"><span className="footer-avatar">{actor.split(' ').map((part) => part[0]).join('').slice(0, 2)}</span><div><strong>{actor}</strong><span>{activePortal === 'analyst' ? 'Analyst · demo identity' : 'Authority · demo identity'}</span></div><ChevronDown size={15} /></div>
      </aside>

      <main className="main-workspace">
        <header className="topbar"><div className="breadcrumbs"><span>Operations</span><span>/</span><strong>{activePortal === 'analyst' ? activeView === 'queue' ? 'Flag review' : activeView === 'audit' ? 'Audit trail' : 'Monthly actions' : 'Authority validation'}</strong></div><div className="topbar-actions"><div className="portal-switch" role="tablist" aria-label="Portal"><button type="button" className={activePortal === 'analyst' ? 'portal-switch-button current' : 'portal-switch-button'} onClick={() => { setActivePortal('analyst'); setActor('R. Mehta'); setActiveView('queue'); setError('') }}><ClipboardCheck size={14} /> Analyst</button><button type="button" className={activePortal === 'authority' ? 'portal-switch-button current authority-current' : 'portal-switch-button'} onClick={() => { setActivePortal('authority'); setActor('P. Rao'); setActiveView('queue'); setError('') }}><ShieldCheck size={14} /> Authority</button></div><span className="env-chip"><span /> DEMO DATA</span><label className="actor-select"><span>ACTOR</span><select value={actor} onChange={(event) => setActor(event.target.value)} aria-label="Current reviewer">{actorOptions.map((reviewer) => <option key={reviewer}>{reviewer}</option>)}</select></label><button className="icon-button" title="Notifications" aria-label="Notifications"><Bell size={17} /><i /></button><span className="profile-avatar">{actor.split(' ').map((part) => part[0]).join('').slice(0, 2)}</span></div></header>
        {activePortal === 'analyst' ? (activeView === 'monthly' ? <div className="page-content">
          <div className="page-heading"><div><div className="eyebrow"><span /> NAGPUR MUNICIPAL CORPORATION · OUTCOME REPORT</div><h1>Monthly authority actions</h1><p>Read-only totals of authority decisions recorded against screening flags.</p></div><button className="quiet-button" onClick={() => void api.corporationMonthlyMetrics(actor, 12).then(setCorporationMetrics)}><RefreshCw size={15} /> Refresh totals</button></div>
          <div className="demo-notice"><ShieldCheck size={15} /><span><strong>Corporation reporting view.</strong> Counts reflect authority decisions and their audit timestamps; analysts cannot change authority outcomes.</span></div>
          {error && <div className="error-banner"><CircleAlert size={16} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={16} /></button></div>}
          <MonthlyActions metrics={corporationMetrics} />
        </div> : <div className="page-content">
          <div className="page-heading"><div><div className="eyebrow"><span /> NAGPUR · URBAN CHANGE MONITORING</div><h1>{activeView === 'queue' ? 'Flag review desk' : 'Audit trail'}</h1><p>{activeView === 'queue' ? 'Review, route, and validate satellite-screening candidates.' : 'A time-ordered record of flag creation, assignments, decisions, and notes.'}</p></div><div className="heading-actions"><button className="quiet-button" onClick={() => void loadFlags()} disabled={refreshing} title="Refresh flags"><RefreshCw size={15} className={refreshing ? 'spinning' : ''} /> Refresh</button><button className="primary-button" onClick={() => setShowCreate(true)}><Plus size={17} /> Create flag</button></div></div>
          <div className="demo-notice"><CircleAlert size={15} /><span><strong>Demonstration workspace.</strong> Seeded records are illustrative only, not verified violations. Sign-in is simulated; configure organizational authentication before real authority decisions.</span></div>
          {error && <div className="error-banner"><CircleAlert size={16} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error"><X size={16} /></button></div>}

          {activeView === 'queue' ? <>
            <section className="metric-strip" aria-label="Queue summary">
              <div className="metric-cell"><span className="metric-icon metric-amber"><Clock3 size={17} /></span><div><span>NEEDS REVIEW</span><strong>{needsReview.toString().padStart(2, '0')}</strong></div><small>analyst queue</small></div>
              <div className="metric-cell"><span className="metric-icon metric-blue"><Send size={17} /></span><div><span>WITH AUTHORITY</span><strong>{withAuthority.toString().padStart(2, '0')}</strong></div><small>awaiting validation</small></div>
              <div className="metric-cell"><span className="metric-icon metric-coral"><CircleAlert size={17} /></span><div><span>HIGH PRIORITY</span><strong>{highPriority.toString().padStart(2, '0')}</strong></div><small>open cases</small></div>
              <div className="metric-cell metric-last"><span className="metric-icon metric-green"><CheckCheck size={17} /></span><div><span>TOTAL FLAGS</span><strong>{flags.length.toString().padStart(2, '0')}</strong></div><small>this workspace</small></div>
            </section>
            <div className="workbench">
              <section className="queue-panel panel-shell">
                <div className="panel-heading queue-heading"><div><span className="section-kicker">CASE REGISTER</span><h2>Flag queue <span>{flags.length}</span></h2></div><button className="small-icon-button" title="Filter queue" aria-label="Filter queue"><Filter size={15} /></button></div>
                <div className="queue-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ID, zone, or signal" /><kbd>/</kbd></div>
                <div className="filter-tabs" role="tablist" aria-label="Filter flags">{statusFilters.map((filter) => <button key={filter.value} className={statusFilter === filter.value ? 'filter-tab selected' : 'filter-tab'} onClick={() => setStatusFilter(filter.value)}>{filter.label}{filter.value === 'needs_review' && <span>{needsReview}</span>}</button>)}</div>
                <div className="queue-list">{loading ? <div className="empty-state">Loading flags…</div> : visibleFlags.length === 0 ? <div className="empty-state">No flags match this filter.</div> : visibleFlags.map((flag) => <button key={flag.id} className={flag.id === selectedId ? 'flag-row active' : 'flag-row'} onClick={() => { setSelectedId(flag.id); setActiveView('queue') }}><div className="flag-row-top"><span className="flag-ref">{flag.reference}</span><span className={`priority-dot priority-${flag.priority}`} title={`${flag.priority} priority`} /></div><strong>{flag.zone_name}</strong><span className="flag-signal">{flag.signal_label}</span><div className="flag-row-bottom"><StatusPill status={flag.status} /><time>{formatDate(flag.created_at)}</time></div></button>)}</div>
                <div className="queue-foot"><span><i className="live-dot" /> SYNCED WITH CASE REGISTER</span><span>{visibleFlags.length} shown</span></div>
              </section>

              <section className="case-panel" aria-label="Selected flag details">{selectedFlag ? <>
                <div className="case-heading"><div className="case-ref-line"><span className="case-ref">{selectedFlag.reference}</span><span className="case-divider">/</span><span>{selectedFlag.zone_name}</span><span className={`priority-label priority-text-${selectedFlag.priority}`}>{selectedFlag.priority} priority</span></div><h2>{selectedFlag.signal_label}</h2><p>{selectedFlag.address}</p><div className="case-meta"><StatusPill status={selectedFlag.status} /><span>Created {formatDate(selectedFlag.created_at)}</span><span>·</span><span>{selectedFlag.area_hectares.toFixed(2)} ha mapped</span></div></div>
                <div className="decision-bar"><span>REVIEW ACTION</span><div><button className="action-button action-authority" onClick={() => void updateFlag({ status: 'authority_review' }, 'Flag sent to authority review')}><Send size={14} /> Send to authority</button><button className="action-button" onClick={() => void updateFlag({ status: 'field_visit' }, 'Field visit requested')}><MapPin size={14} /> Field visit</button><button className="action-square action-confirm" title="Confirm signal" aria-label="Confirm signal" onClick={() => void updateFlag({ status: 'confirmed' }, 'Flag marked confirmed')}><Check size={16} /></button><button className="action-square action-dismiss" title="Mark not confirmed" aria-label="Mark not confirmed" onClick={() => void updateFlag({ status: 'not_confirmed' }, 'Flag marked not confirmed')}><XCircle size={16} /></button></div></div>
                <div className="case-body-grid">
                  <div className="evidence-column"><div className="subsection-heading"><h3>Location evidence</h3><span className="mono-coords">{selectedFlag.latitude.toFixed(5)}° N&nbsp; {selectedFlag.longitude.toFixed(5)}° E</span></div>
                    <div className="map-frame"><LocationMap flag={selectedFlag} /><span className="map-scale">NAGPUR · INDIA <span>10 m</span></span></div>
                    <div className="evidence-stats"><div><span>EST. AREA</span><strong>{selectedFlag.area_hectares.toFixed(2)} <small>ha</small></strong></div><div><span>SIGNAL INDEX</span><div className="signal-meter" aria-label={`Signal index ${selectedFlag.signal_index} out of 100`}><span><i style={{ width: `${selectedFlag.signal_index}%` }} /></span><b>{selectedFlag.signal_index}</b></div></div><div><span>SCREENING SOURCE</span><strong className="source-text">Sentinel-2 L2A</strong></div></div>
                    <div className="scene-pair"><div className="scene-head"><h3>Scene comparison</h3><span>10 m GSD · optical</span></div><div className="scene-cards"><div className="scene-card scene-before"><div className="scene-placeholder"><span className="preview-tag">DEMO PREVIEW</span><span className="scene-grid" /><span className="scene-marker" /></div><div className="scene-caption"><span>EPOCH T0</span><strong>{formatDate(selectedFlag.epoch_t0)}</strong><small>Sentinel-2 MSI · L2A</small></div></div><div className="scene-arrow"><ArrowRight size={15} /></div><div className="scene-card scene-after"><div className="scene-placeholder"><span className="preview-tag">DEMO PREVIEW</span><span className="scene-grid" /><span className="scene-marker" /></div><div className="scene-caption"><span>EPOCH T1</span><strong>{formatDate(selectedFlag.epoch_t1)}</strong><small>Sentinel-2 MSI · L2A</small></div></div></div><p className="evidence-summary">{selectedFlag.evidence_summary}</p></div>
                  </div>
                  <aside className="review-column"><div className="subsection-heading"><h3>Validation</h3><span className="review-seal"><ShieldCheck size={14} /> CONTROLLED</span></div>
                    <div className="review-field"><label htmlFor="assignee">ASSIGNED REVIEWER</label><div className="select-wrap"><select id="assignee" value={selectedFlag.assignee ?? ''} onChange={(event) => void updateFlag({ assignee: event.target.value, status: event.target.value ? 'assigned' : 'triage' }, `Assigned to ${event.target.value || 'unassigned'}`)}><option value="">Unassigned</option>{reviewers.map((reviewer) => <option key={reviewer}>{reviewer}</option>)}</select><ChevronDown size={14} /></div></div>
                    <div className="review-field"><label htmlFor="priority">PRIORITY</label><div className="select-wrap"><select id="priority" value={selectedFlag.priority} onChange={(event) => void updateFlag({ priority: event.target.value as FlagPriority }, `Priority changed to ${event.target.value}`)}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></select><ChevronDown size={14} /></div></div>
                    <div className="validation-box"><div className="validation-title"><ClipboardCheck size={16} /><strong>Permit check</strong><span className="pending-badge">PENDING</span></div><p>Compare this location with the approved building permission and sanctioned plan before making a determination.</p><button onClick={() => void updateFlag({ status: 'authority_review' }, 'Permit check assigned to authority')}>Route for permit check <ArrowRight size={14} /></button></div>
                    <div className="reviewer-note"><span>DECISION GUIDANCE</span><p>Satellite screening is an investigative lead only. A reviewer must validate the evidence and permit record.</p></div>
                  </aside>
                </div>
              </> : <div className="empty-state">Select a flag to review its evidence.</div>}</section>

              <aside className="activity-panel panel-shell"><div className="panel-heading"><div><span className="section-kicker">APPEND-ONLY EVENT LOG</span><h2>Audit trail</h2></div><button className="small-icon-button" title="View full audit trail" aria-label="View full audit trail" onClick={() => setActiveView('audit')}><ArrowDownUp size={15} /></button></div><div className="activity-context"><span className="activity-case-dot" /><div><strong>{selectedFlag?.reference ?? 'No case selected'}</strong><span>Flag activity</span></div></div><div className="audit-list">{audit.map((event) => <AuditLine key={event.id} event={event} />)}{audit.length === 0 && <div className="empty-state compact">No activity recorded.</div>}</div><form className="note-composer" onSubmit={addNote}><label htmlFor="review-note">ADD REVIEW NOTE</label><textarea id="review-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Record a review observation…" rows={3} /><div><span>Added to permanent case history</span><button className="send-note" type="submit" disabled={!note.trim()} title="Add note" aria-label="Add note"><Send size={15} /></button></div></form></aside>
            </div>
          </> : <section className="global-audit panel-shell"><div className="panel-heading"><div><span className="section-kicker">APPEND-ONLY REGISTER</span><h2>All audit events <span>{globalAudit.length}</span></h2></div><div className="audit-legend"><span><i className="legend-blue" /> Status / assignment</span><span><i className="legend-green" /> Notes</span></div></div><div className="global-audit-table"><div className="audit-table-head"><span>EVENT</span><span>CASE</span><span>ACTOR</span><span>DETAIL</span><span>TIMESTAMP</span></div>{globalAudit.map((event) => <div key={event.id} className="audit-table-row"><span className="event-kind"><i className={event.action === 'NOTE_ADDED' ? 'legend-green' : 'legend-blue'} />{event.action.replaceAll('_', ' ')}</span><strong>{event.flag_reference}</strong><span>{event.actor}</span><span>{event.summary}{event.note ? ` · ${event.note}` : ''}</span><time>{formatTimestamp(event.created_at)}</time></div>)}{globalAudit.length === 0 && <div className="empty-state">No audit events have been recorded.</div>}</div></section>}
          <footer className="workspace-footer"><span><ShieldCheck size={14} /> Every change is recorded with actor and timestamp</span><span>ABHILEKH · CASE MANAGEMENT PILOT</span></footer>
        </div>) : <AuthorityPortal actor={actor} error={error} onError={setError} />}
      </main>

      {showCreate && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowCreate(false) }}><section className="create-modal" role="dialog" aria-modal="true" aria-labelledby="create-title"><div className="modal-heading"><div><span className="section-kicker">NEW SCREENING CASE</span><h2 id="create-title">Create a flag</h2></div><button className="small-icon-button" onClick={() => setShowCreate(false)} aria-label="Close"><X size={17} /></button></div><form onSubmit={createFlag}><div className="form-grid"><label>Zone<input name="zone_name" placeholder="e.g. Laxmi Nagar, Zone 1" required /></label><label>Signal type<select name="signal_label"><option>Built-surface gain</option><option>Land clearing</option><option>SAR-supported change</option><option>Manual field observation</option></select></label><label className="wide-field">Address / landmark<input name="address" placeholder="Street, parcel, or nearby landmark" required /></label><label>Latitude<input name="latitude" type="number" step="any" defaultValue="21.1215" required /></label><label>Longitude<input name="longitude" type="number" step="any" defaultValue="79.0645" required /></label><label>Approx. area (ha)<input name="area_hectares" type="number" min="0" step="0.01" defaultValue="0.03" required /></label><label>Signal index<input name="signal_index" type="number" min="0" max="100" defaultValue="62" required /></label><label>Epoch T0<input name="epoch_t0" type="date" defaultValue="2025-10-01" required /></label><label>Epoch T1<input name="epoch_t1" type="date" defaultValue="2026-09-25" required /></label><label className="wide-field">Evidence summary<textarea name="evidence_summary" rows={3} defaultValue="Candidate generated for analyst review. Verify image quality, mapped footprint, and permit records." required /></label></div><div className="modal-actions"><span>New flags start in analyst review</span><button className="quiet-button" type="button" onClick={() => setShowCreate(false)}>Cancel</button><button className="primary-button" type="submit"><Plus size={16} /> Create flag</button></div></form></section></div>}
      {toast && <div className="toast"><Check size={15} />{toast}</div>}
    </div>
  )
}

export default App
