import { INPUT_CLASS } from "@/lib/styles";

export function TestCallModal({
  isOpen,
  onClose,
  testPhone,
  setTestPhone,
  testCallState,
  setTestCallState,
  testCallMsg,
  handleTestCall,
}: {
  isOpen: boolean;
  onClose: () => void;
  testPhone: string;
  setTestPhone: (v: string) => void;
  testCallState: "idle" | "loading" | "success" | "error";
  setTestCallState: (v: "idle" | "loading" | "success" | "error") => void;
  testCallMsg: string;
  handleTestCall: () => void;
}) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-background rounded-lg border border-border shadow-xl p-6 w-full max-w-md mx-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">Test Call</h3>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-lg leading-none"
          >
            ×
          </button>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Enter a phone number to initiate a live test call through this campaign.
          Powerline will call you and walk through the full call flow.
        </p>
        <div className="flex gap-2 mb-3">
          <input
            type="tel"
            className={INPUT_CLASS}
            value={testPhone}
            onChange={(e) => {
              setTestPhone(e.target.value);
              setTestCallState("idle");
            }}
            placeholder="+15551234567"
            autoFocus
          />
          <button
            onClick={handleTestCall}
            disabled={testCallState === "loading" || !testPhone.trim()}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity whitespace-nowrap"
          >
            {testCallState === "loading" ? "Calling…" : "Call Me"}
          </button>
        </div>
        {testCallState === "success" && (
          <p className="text-sm text-[#F2542D] mt-1">{testCallMsg}</p>
        )}
        {testCallState === "error" && (
          <p className="text-sm text-destructive mt-1">{testCallMsg}</p>
        )}
      </div>
    </div>
  );
}
