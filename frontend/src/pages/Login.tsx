import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { BUTTON_PRIMARY, CARD_CLASS, FOCUS_RING, INPUT_CLASS, PAGE_HEADING } from "@/lib/styles";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setIsLoading(true);
    try {
      await login(email, password);
    } catch {
      setError("Invalid email or password.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-page-bg">
      <div className={`w-full max-w-sm space-y-6 ${CARD_CLASS} p-8`}>
        <div className="space-y-1">
          <h1 className={PAGE_HEADING}>Powerline</h1>
          <p className="text-sm text-brand-grey-dark">Sign in to your account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <label className="text-sm font-medium text-brand-black" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={INPUT_CLASS}
              placeholder="admin@example.com"
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-brand-black" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>

          {error && <p className="text-sm text-brand-grey-dark">{error}</p>}

          <button
            type="submit"
            disabled={isLoading}
            className={`${BUTTON_PRIMARY} w-full`}
          >
            {isLoading ? "Signing in…" : "Sign in"}
          </button>

          <div className="flex justify-center">
            <Link
              to="/reset-password"
              className={`flex min-h-[44px] items-center rounded-control px-2 text-sm text-brand-grey-dark hover:underline ${FOCUS_RING}`}
            >
              Forgot password?
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
