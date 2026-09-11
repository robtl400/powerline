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
  /** Levels of government to route calls to via ZIP lookup (from embed_config). */
  target_levels?: string[];
}

export interface RepInfo {
  name: string;
  title: string;
  level: string;
  /** Opaque, short-lived handle for the selected representative. */
  rep_token: string;
}

export interface RepsResponse {
  reps: RepInfo[];
  message?: string | null;
}

/**
 * The target the backend will actually dial first. Campaigns may shuffle their
 * dial order, so the connected screen names this rather than the first entry of
 * the public target list.
 */
export interface FirstTarget {
  name: string;
  title: string;
}

export interface VoiceTokenResponse {
  token: string;
  /** Session UUID — passed to device.connect({ params: { session_id } }). */
  session_id: string;
  first_target?: FirstTarget | null;
}

export interface CallCreateResponse {
  session_id: string;
  status: string;
  first_target?: FirstTarget | null;
}

/**
 * Widget state machine.
 *
 * idle           → user sees zip input + "Call Now" button
 * loading         → fetching token / placing call
 * mic_permission  → waiting for browser mic grant
 * audio_check     → connected but no audio detected; show troubleshooting
 * connected       → in a live call with a target
 * complete        → all targets called
 * error           → unrecoverable error; show message + retry
 * phone_input     → user chose phone fallback; entering number
 * phone_pending   → phone callback placed; waiting for call
 * lookingUpReps   → spinner while fetching reps from backend
 * repSelection    → showing rep list for the user to pick
 */
export type WidgetState =
  | "idle"
  | "loading"
  | "mic_permission"
  | "audio_check"
  | "connected"
  | "complete"
  | "error"
  | "phone_input"
  | "phone_pending"
  | "lookingUpReps"
  | "repSelection";

/** Payload carried alongside an "error" state change. */
export interface ErrorDetail {
  message: string;
  /** Machine-readable backend code, when the response carried one. */
  code?: string;
}

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
