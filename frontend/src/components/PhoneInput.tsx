/**
 * US-only phone input. Accepts 10 digits, auto-formats to (XXX) XXX-XXXX.
 * Calls onChange with E.164 value (+1XXXXXXXXXX) on every change.
 * The +1 prefix is never typed by the user.
 */

import React from "react";

export function formatPhoneInput(raw: string): string {
  // raw = digits only (up to 10)
  const digits = raw.replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  if (digits.length < 3) return `(${digits}`;
  if (digits.length === 3) return `(${digits})`;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
}

export function toE164(formatted: string): string {
  const digits = formatted.replace(/\D/g, "").slice(0, 10);
  if (digits.length === 0) return "";
  return `+1${digits}`;
}

export function validatePhone(e164: string): boolean {
  return /^\+1\d{10}$/.test(e164);
}

interface PhoneInputProps {
  value: string; // E.164 or empty
  onChange: (e164: string) => void;
  required?: boolean;
  placeholder?: string;
  className?: string;
}

export function PhoneInput({ value, onChange, required, placeholder = "(555) 555-5555", className }: PhoneInputProps) {
  const [touched, setTouched] = React.useState(false);

  // Derive display value from E.164
  const digits = value.startsWith("+1") ? value.slice(2) : value.replace(/\D/g, "");
  const display = formatPhoneInput(digits);

  const isInvalid = touched && value.length > 0 && !validatePhone(value);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const raw = e.target.value.replace(/\D/g, "");
    const formatted = formatPhoneInput(raw);
    onChange(toE164(formatted));
  }

  // Handle paste: strip +1 prefix if present, then format
  function handlePaste(e: React.ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    let pasted = e.clipboardData.getData("text").replace(/\D/g, "");
    if (pasted.startsWith("1") && pasted.length === 11) {
      pasted = pasted.slice(1);
    }
    const formatted = formatPhoneInput(pasted);
    onChange(toE164(formatted));
    setTouched(true);
  }

  return (
    <div className={className}>
      <div
        className={`flex rounded-lg border bg-background text-sm focus-within:ring-2 focus-within:ring-brand-black focus-within:ring-offset-0 ${
          isInvalid ? "border-brand-grey-dark" : "border-brand-border"
        }`}
      >
        {/* Prefix box */}
        <div className="flex items-center gap-1 px-3 bg-page-bg border-r border-brand-border rounded-l-lg text-brand-grey-dark select-none whitespace-nowrap">
          🇺🇸 +1
        </div>
        <input
          type="tel"
          inputMode="tel"
          maxLength={14}
          autoComplete="tel"
          required={required}
          value={display}
          onChange={handleChange}
          onPaste={handlePaste}
          onBlur={() => setTouched(true)}
          placeholder={placeholder}
          className="flex-1 px-3 py-2 bg-transparent focus:outline-none rounded-r-lg"
        />
      </div>
      {isInvalid && (
        <p className="mt-1 text-[11px] text-brand-grey-dark">
          Enter a 10-digit US phone number
        </p>
      )}
    </div>
  );
}
