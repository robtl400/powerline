import { Suspense, lazy } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import DashboardShell from "@/components/DashboardShell";
import Login from "@/pages/Login";
import ResetPassword from "@/pages/ResetPassword";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Users = lazy(() => import("@/pages/Users"));
const Campaigns = lazy(() => import("@/pages/Campaigns"));
const CampaignEdit = lazy(() => import("@/pages/CampaignEdit"));
const CampaignWizard = lazy(() => import("@/components/campaign/CampaignWizard"));
const PhoneNumbers = lazy(() => import("@/pages/PhoneNumbers"));
const Blocklist = lazy(() => import("@/pages/Blocklist"));
const CallLog = lazy(() => import("@/pages/CallLog"));

function RouteFallback() {
  return (
    <p role="status" className="py-10 text-center text-[13px] text-brand-grey-dark">
      Loading…
    </p>
  );
}

function SuspendedOutlet() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Outlet />
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* Protected: wrap with shell layout */}
          <Route element={<ProtectedRoute />}>
            <Route element={<DashboardShell />}>
              <Route element={<SuspendedOutlet />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/users" element={<Users />} />
                <Route path="/campaigns" element={<Campaigns />} />
                <Route path="/campaigns/new" element={<CampaignWizard />} />
                <Route path="/campaigns/:id/edit" element={<CampaignEdit />} />
                <Route path="/campaigns/:id/wizard" element={<CampaignWizard />} />
                <Route path="/campaigns/:id/calls" element={<CallLog />} />
                <Route path="/phone-numbers" element={<PhoneNumbers />} />
                <Route path="/blocklist" element={<Blocklist />} />
              </Route>
            </Route>
          </Route>
        </Routes>
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#111111",
              color: "#FFFFFF",
              borderRadius: "8px",
              padding: "10px 14px",
              fontSize: "13px",
            },
            duration: 2000,
          }}
        />
      </AuthProvider>
    </BrowserRouter>
  );
}
