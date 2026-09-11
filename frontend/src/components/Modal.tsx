import { useRef } from "react";
import { useDialogBehaviour } from "@/hooks/useDialogBehaviour";
import { CARD_CLASS, FOCUS_RING } from "@/lib/styles";

export function Modal({
  open,
  onClose,
  titleId,
  title,
  children,
  className = "",
}: {
  open: boolean;
  onClose: () => void;
  titleId: string;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useDialogBehaviour({ open, onClose, containerRef: panelRef });

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative max-h-[90vh] w-full max-w-[min(480px,90vw)] overflow-y-auto ${CARD_CLASS} p-6 ${className}`}
      >
        <h2 id={titleId} className="mb-4 pr-10 text-base font-semibold">
          {title}
        </h2>
        {children}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className={`absolute right-2 top-2 inline-flex h-11 w-11 items-center justify-center rounded-control text-lg leading-none text-brand-grey-dark hover:text-brand-black ${FOCUS_RING}`}
        >
          ×
        </button>
      </div>
    </div>
  );
}
