// Shared color-class mappings for status badges.
// Any new status/type values should be added here so all pages stay in sync.

export const CAMPAIGN_STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-700",
  live: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  archived: "bg-red-100 text-red-700",
};

export const CALL_SESSION_STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  initiated: "bg-blue-100 text-blue-700",
  in_progress: "bg-yellow-100 text-yellow-700",
  failed: "bg-red-100 text-red-700",
};

export const CONNECTION_TYPE_COLORS: Record<string, string> = {
  webrtc: "bg-purple-100 text-purple-700",
  outbound_phone: "bg-sky-100 text-sky-700",
  inbound_phone: "bg-teal-100 text-teal-700",
};

export const TRUST_STATUS_COLORS: Record<string, string> = {
  verified: "bg-green-100 text-green-700",
  pending: "bg-yellow-100 text-yellow-700",
  unknown: "bg-gray-100 text-gray-600",
};

export const FALLBACK_BADGE_COLOR = "bg-gray-100 text-gray-700";

// Campaign status machine — mirrors backend VALID_TRANSITIONS
export const VALID_TRANSITIONS: Record<string, string[]> = {
  draft: ["paused", "live"],
  paused: ["live", "archived"],
  live: ["paused", "archived"],
  archived: [],
};

export const STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  paused: "Paused",
  live: "Live",
  archived: "Archived",
};

export const AUDIO_SLOTS = [
  { key: "msg_intro", label: "Intro Greeting", hint: "Played when the call connects." },
  { key: "msg_intro_confirm", label: "Intro Confirm", hint: "Prompts the caller to press any key to begin." },
  { key: "msg_call_block_intro", label: "Block Intro", hint: "Played before dialing the first target." },
  { key: "msg_target_intro", label: "Target Intro", hint: "Announces the target. Use {{title}}, {{name}}, {{location}}." },
  { key: "msg_between_calls", label: "Between Calls", hint: "Played between targets. Use {{calls_left}} for count." },
  { key: "msg_target_busy", label: "Target Busy", hint: "Played when the target doesn't answer." },
  { key: "msg_goodbye", label: "Goodbye", hint: "Played after the last call." },
] as const;
