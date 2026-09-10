import { useRef } from "react";
import { useDialogBehaviour } from "@/hooks/useDialogBehaviour";

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
        className={`relative w-full max-w-[min(480px,90vw)] rounded-[10px] border border-brand-border bg-white p-6 shadow-[0_1px_3px_rgba(0,0,0,0.06),0_1px_2px_rgba(0,0,0,0.04)] ${className}`}
      >
        <h2 id={titleId} className="mb-4 pr-6 text-base font-semibold">
          {title}
        </h2>
        {children}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-5 top-5 text-lg leading-none text-brand-grey-dark hover:text-brand-black"
        >
          ×
        </button>
      </div>
    </div>
  );
}
