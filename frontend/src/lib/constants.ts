// Shared color-class mappings for status badges.
// Any new status/type values should be added here so all pages stay in sync.

// Tailwind class-based mappings kept for simpler badge use
export const CAMPAIGN_STATUS_COLORS: Record<string, string> = {
  draft:    "bg-[#F9FAFB] text-[#92918F] border border-[#E4E6EC]",
  live:     "bg-[rgba(242,84,45,0.10)] text-[#F2542D] border border-[rgba(242,84,45,0.25)]",
  paused:   "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  archived: "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  completed:"bg-[rgba(176,83,87,0.10)] text-[#B05357] border border-[rgba(176,83,87,0.20)]",
  failed:   "bg-[#F3F4F6] text-[#53565B] border border-[#D1D3D9]",
};

export const CALL_SESSION_STATUS_COLORS: Record<string, string> = {
  completed:   "bg-[rgba(176,83,87,0.10)] text-[#B05357] border border-[rgba(176,83,87,0.20)]",
  initiated:   "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  in_progress: "bg-[rgba(242,84,45,0.10)] text-[#F2542D] border border-[rgba(242,84,45,0.25)]",
  failed:      "bg-[#F3F4F6] text-[#53565B] border border-[#D1D3D9]",
};

export const CONNECTION_TYPE_COLORS: Record<string, string> = {
  webrtc:         "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  outbound_phone: "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  inbound_phone:  "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
};

// Twilio trust_status values as they arrive from the API
export const TRUST_STATUS_COLORS: Record<string, string> = {
  "twilio-approved": "bg-[rgba(176,83,87,0.10)] text-[#B05357] border border-[rgba(176,83,87,0.20)]",
  "pending-review":  "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  "in-review":       "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
  unknown:           "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]",
};

export const TRUST_STATUS_LABELS: Record<string, string> = {
  "twilio-approved": "Verified",
  "pending-review":  "Pending",
  "in-review":       "Pending",
  unknown:           "Unknown",
};

export const FALLBACK_BADGE_COLOR = "bg-[#F4F5F7] text-[#92918F] border border-[#E4E6EC]";

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
