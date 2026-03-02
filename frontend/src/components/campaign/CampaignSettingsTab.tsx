import { STATUS_LABELS } from "@/lib/constants";
import { INPUT_CLASS } from "@/lib/styles";
import type { CampaignChecklist, CampaignForm } from "@/types/campaign";

type TabType = "settings" | "targets" | "audio" | "embed" | "stats";

export function CampaignSettingsTab({
  form,
  setForm,
  status,
  isNew,
  saving,
  handleSave,
  statusMenuOpen,
  setStatusMenuOpen,
  pendingStatus,
  setPendingStatus,
  openStatusMenu,
  confirmStatusChange,
  nextStatuses,
  checklist,
  checklistLoading,
  onTabChange,
  onOpenTestCall,
}: {
  form: CampaignForm;
  setForm: (fn: (prev: CampaignForm) => CampaignForm) => void;
  status: string;
  isNew: boolean;
  saving: boolean;
  handleSave: () => void;
  statusMenuOpen: boolean;
  setStatusMenuOpen: (v: boolean) => void;
  pendingStatus: string | null;
  setPendingStatus: (v: string | null) => void;
  openStatusMenu: () => void;
  confirmStatusChange: () => void;
  nextStatuses: string[];
  checklist: CampaignChecklist | null;
  checklistLoading: boolean;
  onTabChange: (tab: TabType) => void;
  onOpenTestCall: () => void;
}) {
  function field(label: string, children: React.ReactNode, hint?: string): React.ReactNode {
    return (
      <div>
        <label className="block text-sm font-medium text-foreground mb-1">{label}</label>
        {children}
        {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      </div>
    );
  }

  function checkbox(label: string, key: keyof CampaignForm, hint?: string): React.ReactNode {
    return (
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={form[key] as boolean}
          onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.checked }))}
        />
        <div>
          <span className="text-sm font-medium">{label}</span>
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
      </label>
    );
  }

  return (
    <div className="space-y-8">
      {/* Basic Info */}
      <section>
        <h2 className="text-base font-semibold mb-4 pb-2 border-b border-border">Basic Info</h2>
        <div className="space-y-4">
          {field(
            "Name *",
            <input
              className={INPUT_CLASS}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Call Your Senator"
            />
          )}
          {field(
            "Description",
            <textarea
              className={INPUT_CLASS}
              rows={3}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Optional description shown internally"
            />
          )}
          <div className="grid grid-cols-2 gap-4">
            {field(
              "Language",
              <select
                className={INPUT_CLASS}
                value={form.language}
                onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
              >
                <option value="en-US">English (en-US)</option>
                <option value="es">Spanish (es)</option>
              </select>
            )}
            {field(
              "Target Ordering",
              <select
                className={INPUT_CLASS}
                value={form.target_ordering}
                onChange={(e) => setForm((f) => ({ ...f, target_ordering: e.target.value }))}
              >
                <option value="in_order">In Order</option>
                <option value="shuffle">Shuffle</option>
              </select>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            {field(
              "Call Maximum",
              <input
                type="number"
                className={INPUT_CLASS}
                value={form.call_maximum}
                onChange={(e) => setForm((f) => ({ ...f, call_maximum: e.target.value }))}
                placeholder="Blank = unlimited"
                min={1}
              />,
              "Max calls per supporter session"
            )}
            {field(
              "Rate Limit (calls/hour)",
              <input
                type="number"
                className={INPUT_CLASS}
                value={form.rate_limit}
                onChange={(e) => setForm((f) => ({ ...f, rate_limit: e.target.value }))}
                placeholder="Blank = unlimited"
                min={1}
              />,
              "Max calls per phone/IP per hour"
            )}
          </div>
        </div>
      </section>

      {/* Connection Modes */}
      <section>
        <h2 className="text-base font-semibold mb-4 pb-2 border-b border-border">
          Connection Modes
        </h2>
        <div className="space-y-3">
          {checkbox("Allow WebRTC (browser calls)", "allow_webrtc", "Supporters call directly from the browser")}
          {checkbox("Allow Phone Callback", "allow_phone_callback", "Powerline calls the supporter's phone, then connects to target")}
          {checkbox("Allow Dial-In", "allow_call_in", "Supporter dials a number to be connected")}
          {checkbox("Validate Phone Numbers (Twilio Lookup)", "lookup_validate")}
          {checkbox("Require Mobile Number", "lookup_require_mobile", "Reject landlines and VoIP")}
        </div>
      </section>

      {/* Talking Points */}
      <section>
        <h2 className="text-base font-semibold mb-4 pb-2 border-b border-border">
          Talking Points
        </h2>
        {field(
          "Talking Points",
          <textarea
            className={INPUT_CLASS}
            rows={6}
            value={form.talking_points}
            onChange={(e) => setForm((f) => ({ ...f, talking_points: e.target.value }))}
            placeholder="• Senator Smith voted against affordable housing last year&#10;• Ask them to support the Housing Affordability Act&#10;• Be polite but firm — every call counts"
          />,
          "Shown to supporters in the call widget to guide their conversation. Supports plain text with bullet points."
        )}
      </section>

      {/* Launch Checklist — shown when campaign is live */}
      {!isNew && status === "live" && (
        <section>
          <h2 className="text-base font-semibold mb-4 pb-2 border-b border-border">
            Launch Checklist
          </h2>
          {checklistLoading && (
            <p className="text-sm text-muted-foreground">Checking…</p>
          )}
          {checklist && (() => {
            const items: { label: string; ok: boolean; tab?: TabType }[] = [
              { label: "Targets configured", ok: checklist.targets_configured, tab: "targets" },
              { label: "Audio set", ok: checklist.audio_configured, tab: "audio" },
              { label: "Phone number assigned", ok: checklist.phone_number_assigned },
              { label: "STIR/SHAKEN verified", ok: checklist.phone_verified },
              { label: "Talking points written", ok: checklist.talking_points_written, tab: "settings" },
            ];
            return (
              <ul className="space-y-2">
                {items.map(({ label, ok, tab }) => (
                  <li key={label} className="flex items-center gap-2 text-sm">
                    <span className={ok ? "text-green-600" : "text-yellow-600"}>
                      {ok ? "✅" : "⚠️"}
                    </span>
                    <span className={ok ? "text-foreground" : "text-muted-foreground"}>
                      {label}
                    </span>
                    {!ok && tab && (
                      <button
                        onClick={() => onTabChange(tab)}
                        className="ml-1 text-xs text-primary hover:underline"
                      >
                        → Fix it
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            );
          })()}
        </section>
      )}

      {/* Test Call button — opens modal when campaign is live */}
      {!isNew && status === "live" && form.allow_phone_callback && (
        <section>
          <h2 className="text-base font-semibold mb-4 pb-2 border-b border-border">
            Test Call
          </h2>
          <p className="text-sm text-muted-foreground mb-3">
            Initiate a live test call to verify the full call flow end-to-end.
          </p>
          <button
            onClick={onOpenTestCall}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
          >
            📞 Open Test Call
          </button>
        </section>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving || !form.name.trim()}
          className="px-5 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {saving ? "Saving…" : "Save Campaign"}
        </button>

        {!isNew && nextStatuses.length > 0 && (
          <div className="relative">
            <button
              onClick={openStatusMenu}
              className="px-4 py-2 border border-border rounded-md text-sm font-medium hover:bg-muted/50 transition-colors"
            >
              Change Status
            </button>
          </div>
        )}
      </div>

      {/* Status change confirmation */}
      {statusMenuOpen && (
        <div className="rounded-md border border-border bg-muted/30 p-4 space-y-3">
          <p className="text-sm font-medium">
            Current status: <span className="font-semibold capitalize">{status}</span>. Choose new
            status:
          </p>
          <div className="flex gap-2 flex-wrap">
            {nextStatuses.map((s) => (
              <button
                key={s}
                onClick={() => setPendingStatus(s)}
                className={`px-3 py-1.5 rounded text-sm font-medium border-2 transition-colors capitalize ${
                  pendingStatus === s
                    ? "border-primary bg-primary/10"
                    : "border-border hover:border-primary/50"
                }`}
              >
                {STATUS_LABELS[s] ?? s}
              </button>
            ))}
          </div>
          {pendingStatus && (
            <div className="flex gap-2">
              <button
                onClick={confirmStatusChange}
                className="px-4 py-1.5 bg-primary text-primary-foreground rounded-md text-sm font-medium"
              >
                Confirm → {STATUS_LABELS[pendingStatus]}
              </button>
              <button
                onClick={() => setStatusMenuOpen(false)}
                className="px-4 py-1.5 border border-border rounded-md text-sm"
              >
                Cancel
              </button>
            </div>
          )}
          {!pendingStatus && (
            <button
              onClick={() => setStatusMenuOpen(false)}
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  );
}
