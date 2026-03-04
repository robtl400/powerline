// Shared color-class mappings for status badges.
// Any new status/type values should be added here so all pages stay in sync.

export const CAMPAIGN_STATUS_COLORS: Record<string, string> = {
  draft:    "bg-stone-100 text-[#53565B]",
  live:     "bg-[#F2542D]/10 text-[#F2542D]",
  paused:   "bg-stone-100 text-[#53565B]",
  archived: "bg-[#F2542D]/10 text-[#F2542D]",
};

export const CALL_SESSION_STATUS_COLORS: Record<string, string> = {
  completed:   "bg-[#F2542D]/10 text-[#F2542D]",
  initiated:   "bg-stone-100 text-[#53565B]",
  in_progress: "bg-[#F2542D]/10 text-[#F2542D]",
  failed:      "bg-red-100 text-red-700",
};

export const CONNECTION_TYPE_COLORS: Record<string, string> = {
  webrtc:         "bg-stone-100 text-[#53565B]",
  outbound_phone: "bg-stone-100 text-[#53565B]",
  inbound_phone:  "bg-stone-100 text-[#53565B]",
};

export const TRUST_STATUS_COLORS: Record<string, string> = {
  verified: "bg-[#F2542D]/10 text-[#F2542D]",
  pending:  "bg-stone-100 text-[#53565B]",
  unknown:  "bg-stone-100 text-[#53565B]",
};

export const FALLBACK_BADGE_COLOR = "bg-stone-100 text-[#53565B]";

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
