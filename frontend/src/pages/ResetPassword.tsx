import { useState, type FormEvent } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import client from "@/api/client";
import { getErrorDetail } from "@/lib/api-error";
import { BUTTON_PRIMARY, CARD_CLASS, FOCUS_RING, INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";

const AUTH_CARD_CLASS = `w-full max-w-sm space-y-6 ${CARD_CLASS} p-8`;

const BUTTON_CLASS = `${BUTTON_PRIMARY} w-full`;

const PASSWORD_POLICY = "12–128 characters, including at least one letter and one digit.";

function messageFor(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 429) {
    return "Too many attempts. Try again in an hour.";
  }
  return getErrorDetail(error);
}

export default function ResetPassword() {
  const [step, setStep] = useState<1 | 2>(1);
  const [done, setDone] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleRequest(e: FormEvent) {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await client.post("/auth/reset-request", { email });
      setStep(2);
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await client.post("/auth/reset-confirm", {
        email,
        code,
        new_password: newPassword,
      });
      setDone(true);
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page-bg">
      <div className={AUTH_CARD_CLASS}>
        <div className="space-y-1">
          <h1 className={PAGE_HEADING}>Reset password</h1>
          {!done && (
            <p className="text-sm text-brand-grey-dark">
              {step === 1
                ? "Enter your email and we'll text a code to the phone on your account."
                : "Enter the code we sent and choose a new password."}
            </p>
          )}
        </div>

        {done ? (
          <div className="space-y-4">
            <p className="text-sm text-brand-grey-dark">
              Your password has been updated.
            </p>
            <Link
              to="/login"
              className={`flex min-h-[44px] items-center justify-center rounded-control bg-brand-orange px-4 text-sm font-medium text-white transition-opacity hover:opacity-90 ${FOCUS_RING}`}
            >
              Sign in
            </Link>
          </div>
        ) : step === 1 ? (
          <form onSubmit={handleRequest} className="space-y-4">
            <div className="space-y-1">
              <label className="text-sm font-medium text-brand-black" htmlFor="reset-email">
                Email
              </label>
              <input
                id="reset-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={INPUT_CLASS}
                placeholder="admin@example.com"
              />
            </div>

            {error && <p className="text-sm text-brand-grey-dark">{error}</p>}

            <button type="submit" disabled={isLoading} className={BUTTON_CLASS}>
              {isLoading ? "Sending…" : "Send code"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleConfirm} className="space-y-4">
            <p className="text-sm text-brand-grey-dark">
              If that email has an account, we sent a code to its phone.
            </p>

            <div className="space-y-1">
              <label className="text-sm font-medium text-brand-black" htmlFor="reset-code">
                Code
              </label>
              <input
                id="reset-code"
                type="text"
                required
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className={INPUT_CLASS}
                placeholder="8-digit code"
              />
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium text-brand-black" htmlFor="reset-password">
                New password
              </label>
              <input
                id="reset-password"
                type="password"
                required
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className={INPUT_CLASS}
              />
              <p className="text-[11px] text-brand-grey-dark">{PASSWORD_POLICY}</p>
            </div>

            {error && <p className="text-sm text-brand-grey-dark">{error}</p>}

            <button type="submit" disabled={isLoading} className={BUTTON_CLASS}>
              {isLoading ? "Saving…" : "Reset password"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
