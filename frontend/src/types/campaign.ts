// Campaign-related TypeScript types shared across CampaignEdit and its sub-components.

export interface Target {
  id: string;
  name: string;
  title: string;
  phone_number: string;
  location: string;
  external_id: string | null;
  target_metadata: Record<string, unknown>;
  order: number;
}

export interface CampaignDetail {
  id: string;
  name: string;
  description: string | null;
  status: string;
  campaign_type: string;
  language: string;
  target_ordering: string;
  call_maximum: number | null;
  rate_limit: number | null;
  allow_call_in: boolean;
  allow_webrtc: boolean;
  allow_phone_callback: boolean;
  lookup_validate: boolean;
  lookup_require_mobile: boolean;
  talking_points: string | null;
  targets: Target[];
}

export interface CampaignForm {
  name: string;
  description: string;
  language: string;
  target_ordering: string;
  call_maximum: string;
  rate_limit: string;
  allow_call_in: boolean;
  allow_webrtc: boolean;
  allow_phone_callback: boolean;
  lookup_validate: boolean;
  lookup_require_mobile: boolean;
  talking_points: string;
}

export interface TargetForm {
  name: string;
  title: string;
  phone_number: string;
  location: string;
  external_id: string;
}

export interface CampaignChecklist {
  targets_configured: boolean;
  audio_configured: boolean;
  phone_number_assigned: boolean;
  phone_verified: boolean;
  talking_points_written: boolean;
}

export interface AudioRecording {
  id: string;
  campaign_id: string | null;
  key: string;
  version: number;
  tts_text: string | null;
  file_url: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface TargetStats {
  target_id: string;
  name: string;
  total_calls: number;
  completed_calls: number;
  avg_duration_seconds: number | null;
}

export interface CampaignStats {
  total_sessions: number;
  completed_sessions: number;
  completion_rate: number;
  avg_calls_per_session: number;
  connection_type_breakdown: Record<string, number>;
  per_target: TargetStats[];
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface QualityData {
  total_calls: number;
  calls_with_quality: number;
  avg_quality_score: number | null;
  connection_rate: number;
  failure_breakdown: Record<string, number>;
}

export const emptyForm = (): CampaignForm => ({
  name: "",
  description: "",
  language: "en-US",
  target_ordering: "in_order",
  call_maximum: "",
  rate_limit: "",
  allow_call_in: false,
  allow_webrtc: true,
  allow_phone_callback: true,
  lookup_validate: true,
  lookup_require_mobile: false,
  talking_points: "",
});

export const emptyTargetForm = (): TargetForm => ({
  name: "",
  title: "",
  phone_number: "",
  location: "",
  external_id: "",
});
