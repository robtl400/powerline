// Shared color-class mappings for status badges.
// Any new status/type values should be added here so all pages stay in sync.

/** Neutral chip surface — the resting state every badge map falls back to. */
export const NEUTRAL_CHIP = "bg-page-bg text-brand-grey-dark border border-brand-border";

const ORANGE_CHIP = "bg-[rgba(242,84,45,0.10)] text-[#F2542D] border border-[rgba(242,84,45,0.25)]";

const GUM_CHIP = "bg-[rgba(176,83,87,0.10)] text-[#B05357] border border-[rgba(176,83,87,0.20)]";

// Tailwind class-based mappings kept for simpler badge use
export const CAMPAIGN_STATUS_COLORS: Record<string, string> = {
  draft:    NEUTRAL_CHIP,
  live:     ORANGE_CHIP,
  paused:   NEUTRAL_CHIP,
  archived: NEUTRAL_CHIP,
  completed:GUM_CHIP,
  failed:   NEUTRAL_CHIP,
};

export const CALL_SESSION_STATUS_COLORS: Record<string, string> = {
  completed:   GUM_CHIP,
  initiated:   NEUTRAL_CHIP,
  in_progress: ORANGE_CHIP,
  failed:      NEUTRAL_CHIP,
};

export const CONNECTION_TYPE_COLORS: Record<string, string> = {
  webrtc:         NEUTRAL_CHIP,
  outbound_phone: NEUTRAL_CHIP,
  inbound_phone:  NEUTRAL_CHIP,
};

// Twilio trust_status values as they arrive from the API
export const TRUST_STATUS_COLORS: Record<string, string> = {
  "twilio-approved": GUM_CHIP,
  "pending-review":  NEUTRAL_CHIP,
  "in-review":       NEUTRAL_CHIP,
  unknown:           NEUTRAL_CHIP,
};

export const TRUST_STATUS_LABELS: Record<string, string> = {
  "twilio-approved": "Verified",
  "pending-review":  "Pending",
  "in-review":       "Pending",
  unknown:           "Unknown",
};

/** Chip surfaces for the AudioSlotCard version badges. */
export const AUDIO_VERSION_BADGE = {
  active: GUM_CHIP,
  inactive: NEUTRAL_CHIP,
} as const;

export const USER_STATUS_COLORS: Record<string, string> = {
  active:   GUM_CHIP,
  inactive: NEUTRAL_CHIP,
};

// Phone-number capability tags are descriptive, not actionable — neutral grey.
export const CAPABILITY_BADGE_COLOR = NEUTRAL_CHIP;

export const FALLBACK_BADGE_COLOR = NEUTRAL_CHIP;

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

/** Largest audio file the upload endpoint accepts, in bytes. */
export const MAX_AUDIO_UPLOAD_BYTES = 10 * 1024 * 1024;

/** Password length bounds enforced by the backend on reset and invite. */
export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

export const AUDIO_SLOTS = [
  { key: "msg_intro", label: "Intro Greeting", hint: "Played when the call connects." },
  { key: "msg_intro_confirm", label: "Intro Confirm", hint: "Prompts the caller to press any key to begin." },
  { key: "msg_call_block_intro", label: "Block Intro", hint: "Played before dialing the first target." },
  { key: "msg_target_intro", label: "Target Intro", hint: "Announces the target. Use {{title}}, {{name}}, {{location}}." },
  { key: "msg_between_calls", label: "Between Calls", hint: "Played between targets. Use {{calls_left}} for count." },
  { key: "msg_target_busy", label: "Target Busy", hint: "Played when the target doesn't answer." },
  { key: "msg_goodbye", label: "Goodbye", hint: "Played after the last call." },
] as const;
