import { Modal } from "@/components/Modal";
import { PhoneInput } from "@/components/PhoneInput";
import { BUTTON_PRIMARY } from "@/lib/styles";

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
  return (
    <Modal open={isOpen} onClose={onClose} titleId="test-call-modal-title" title="Test Call">
      <p className="text-sm text-brand-grey-dark mb-4">
        Enter a phone number to initiate a live test call through this campaign.
        Powerline will call you and walk through the full call flow.
      </p>
      <div className="flex gap-2 mb-3">
        <PhoneInput
          value={testPhone}
          onChange={(v) => {
            setTestPhone(v);
            setTestCallState("idle");
          }}
          className="flex-1"
        />
        <button
          onClick={handleTestCall}
          disabled={testCallState === "loading" || !testPhone.trim()}
          className={`${BUTTON_PRIMARY} whitespace-nowrap`}
        >
          {testCallState === "loading" ? "Calling…" : "Call Me"}
        </button>
      </div>
      {testCallState === "success" && (
        <p className="text-sm text-brand-gum mt-1">{testCallMsg}</p>
      )}
      {testCallState === "error" && (
        <p className="text-sm text-brand-grey-dark mt-1">{testCallMsg}</p>
      )}
    </Modal>
  );
}
