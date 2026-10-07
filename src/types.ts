export type FlagStatus = 'new' | 'triage' | 'assigned' | 'authority_review' | 'field_visit' | 'confirmed' | 'not_confirmed' | 'closed' | 'action_taken' | 'not_illegal'
export type FlagPriority = 'low' | 'normal' | 'high'
export type PortalRole = 'analyst' | 'authority'
export type AuthorityOutcome = 'action_taken' | 'not_illegal'

export interface Flag {
  id: string
  reference: string
  zone_name: string
  address: string
  signal_label: string
  latitude: number
  longitude: number
  area_hectares: number
  signal_index: number
  epoch_t0: string
  epoch_t1: string
  evidence_summary: string
  status: FlagStatus
  priority: FlagPriority
  assignee: string | null
  corporation_name: string
  created_at: string
  updated_at: string
}

export interface AuditEvent {
  id: number
  flag_id: string
  flag_reference: string
  action: string
  actor: string
  actor_role: PortalRole | 'system'
  summary: string
  note: string | null
  created_at: string
}

export interface CreateFlag {
  zone_name: string
  address: string
  signal_label: string
  latitude: number
  longitude: number
  area_hectares: number
  signal_index: number
  epoch_t0: string
  epoch_t1: string
  evidence_summary: string
}

export interface MonthlyAuthorityItem {
  month: string
  action_taken: number
  not_illegal: number
}

export interface MonthlyAuthorityCorporation {
  corporation_name: string
  items: MonthlyAuthorityItem[]
}

export interface MonthlyAuthorityMetrics {
  months: string[]
  corporations: MonthlyAuthorityCorporation[]
}