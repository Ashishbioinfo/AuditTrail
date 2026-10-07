import type { AuditEvent, AuthorityOutcome, CreateFlag, Flag, FlagPriority, FlagStatus, MonthlyAuthorityMetrics, PortalRole } from './types'

const base = '/api'

async function request<T>(path: string, actor?: string, role: PortalRole = 'analyst', init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(actor ? { 'X-Actor': actor } : {}),
      'X-Role': role,
      ...init?.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  listFlags: (role: PortalRole = 'analyst') => request<Flag[]>('/flags', undefined, role),
  listFlagAudit: (id: string, role: PortalRole = 'analyst') => request<AuditEvent[]>(role === 'authority' ? `/authority/flags/${id}/audit` : `/flags/${id}/audit`, undefined, role),
  listAudit: () => request<AuditEvent[]>('/audit'),
  listAuthorityFlags: (actor: string) => request<Flag[]>('/authority/flags', actor, 'authority'),
  authorityMonthlyMetrics: (actor: string, months = 12) => request<MonthlyAuthorityMetrics>(`/authority/metrics/monthly?months=${months}`, actor, 'authority'),
  corporationMonthlyMetrics: (actor: string, months = 12) => request<MonthlyAuthorityMetrics>(`/corporation/metrics/monthly?months=${months}`, actor, 'analyst'),
  authorityDecision: (id: string, outcome: AuthorityOutcome, comment: string, actor: string) => request<Flag>(`/authority/flags/${id}/decision`, actor, 'authority', { method: 'POST', body: JSON.stringify({ outcome, comment }) }),
  createFlag: (flag: CreateFlag, actor: string) => request<Flag>('/flags', actor, 'analyst', { method: 'POST', body: JSON.stringify(flag) }),
  updateFlag: (id: string, changes: { status?: FlagStatus; assignee?: string; priority?: FlagPriority }, actor: string) => request<Flag>(`/flags/${id}`, actor, 'analyst', { method: 'PATCH', body: JSON.stringify(changes) }),
  addNote: (id: string, note: string, actor: string) => request<AuditEvent>(`/flags/${id}/notes`, actor, 'analyst', { method: 'POST', body: JSON.stringify({ note }) }),
}