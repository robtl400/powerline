/** Types shared across the embed SDK. */

export interface TargetPublicInfo {
  id: string;
  name: string;
  title: string;
  location: string;
}

export interface CampaignPublic {
  id: string;
  name: string;
  description: string | null;
  talking_points: string | null;
  allow_webrtc: boolean;
  allow_phone_callback: boolean;
  targets: TargetPublicInfo[];
}

export interface VoiceTokenResponse {
  token: string;
  /** Session UUID — passed to device.connect({ params: { session_id } }). */
  session_id: string;
}

export interface CallCreateResponse {
  session_id: string;
  status: string;
}

/**
 * Widget state machine.
 *
 * idle         → user sees "Call Now" button
 * loading      → fetching token / placing call
 * mic_permission → waiting for browser mic grant
 * audio_check  → connected but no audio detected; show troubleshooting
 * connected    → in a live call with a target
 * between_targets → transitioning to next target
 * complete     → all targets called
 * error        → unrecoverable error; show message + retry
 * phone_input  → user chose phone fallback; entering number
 * phone_pending → phone callback placed; waiting for call
 */
export type WidgetState =
  | "idle"
  | "loading"
  | "mic_permission"
  | "audio_check"
  | "connected"
  | "between_targets"
  | "complete"
  | "error"
  | "phone_input"
  | "phone_pending";

export interface ConnectedData {
  target: TargetPublicInfo;
  targetIndex: number;
  totalTargets: number;
}

export interface CallCountResponse {
  total: number;
  last_24h: number;
  last_7d: number;
}
