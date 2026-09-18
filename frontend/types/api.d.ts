// TypeScript shapes of the REST API (for a future typed frontend). Kept in sync with backend/app/api/serializers.py
export interface ApiResponse<T> { success: true; data: T; meta?: { page: number; page_size: number; total: number } }
export interface ApiError { success: false; error: { code: string; message: string } }
export type DemandLevel = "VERY_HIGH" | "HIGH" | "MEDIUM" | "MODERATE" | "LOW";
export interface EventSummary { id: number; canonical_event_id: string; title: string; category: string; subcategory?: string; date_start: string; date_end?: string;
  time_start?: string; time_end?: string; timezone: string; venue: { id?: number; name?: string; capacity?: number }; city?: string; region?: string; postcode?: string;
  latitude?: number; longitude?: number; status: string; opportunity_score: number; demand_level: DemandLevel; marketing_priority?: "P1" | "P2" | "P3"; primary_source?: string;
  official_url?: string; ticket_url?: string; last_updated_at?: string }
export interface Opportunity { id: number; event_id: number; opportunity_type: string; score: number; demand_level: DemandLevel; window: { start?: string; end?: string; label: string }; reasons: string[]; recommended_action?: string; event?: EventSummary }
export interface MarketingAction { id: number; event_id: number; action_type: string; priority: string; title: string; description?: string; suggested_keyword?: string; suggested_audience?: string; suggested_channel?: string; recommended_time?: string; status: "NEW" | "PLANNED" | "IN_PROGRESS" | "DONE" | "DISMISSED"; scheduled_for?: string }
