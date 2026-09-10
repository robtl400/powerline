import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import DashboardShell from "@/components/DashboardShell";
import Login from "@/pages/Login";
import ResetPassword from "@/pages/ResetPassword";
import Dashboard from "@/pages/Dashboard";
import Users from "@/pages/Users";
import Campaigns from "@/pages/Campaigns";
import CampaignEdit from "@/pages/CampaignEdit";
import CampaignWizard from "@/components/campaign/CampaignWizard";
import PhoneNumbers from "@/pages/PhoneNumbers";
import Blocklist from "@/pages/Blocklist";
import CallLog from "@/pages/CallLog";

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
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/users" element={<Users />} />
              <Route path="/campaigns" element={<Campaigns />} />
              <Route path="/campaigns/new" element={<CampaignEdit />} />
              <Route path="/campaigns/:id/edit" element={<CampaignEdit />} />
              <Route path="/campaigns/:id/wizard" element={<CampaignWizard />} />
              <Route path="/campaigns/:id/calls" element={<CallLog />} />
              <Route path="/phone-numbers" element={<PhoneNumbers />} />
              <Route path="/blocklist" element={<Blocklist />} />
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
