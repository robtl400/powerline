import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Megaphone,
  Phone,
  Users,
  ShieldOff,
  LogOut,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/campaigns", label: "Campaigns", icon: Megaphone },
  { to: "/phone-numbers", label: "Phone Numbers", icon: Phone },
  { to: "/users", label: "Users", icon: Users },
  { to: "/blocklist", label: "Blocklist", icon: ShieldOff },
];

export default function DashboardShell() {
  const { user, logout } = useAuth();

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Full-width top bar + powerlines */}
      <div className="flex flex-col bg-background">
        <div className="flex h-14">
          <div className="flex w-56 items-center px-4">
            <span className="text-2xl font-black tracking-normal text-[#111111]">Powerline</span>
          </div>
          <header className="flex flex-1 items-center justify-between px-6">
            <div />
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground">{user?.name}</span>
              <button
                onClick={logout}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                <LogOut className="h-4 w-4" />
                Logout
              </button>
            </div>
          </header>
        </div>
        {/* Powerlines decoration — full width */}
        <div aria-hidden="true" style={{ lineHeight: 0, overflow: "hidden" }}>
          <svg
            viewBox="0 0 1440 30"
            preserveAspectRatio="none"
            width="100%"
            height="24"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M 0,22 Q 720,2 1440,18" stroke="#6b7280" strokeWidth="1.5"/>
            <path d="M 0,8 Q 720,28 1440,12" stroke="#6b7280" strokeWidth="1.5"/>
            <path d="M 0,15 Q 600,6 1440,24" stroke="#6b7280" strokeWidth="1.5"/>
          </svg>
        </div>
      </div>

      {/* Content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <aside className="flex w-56 flex-col border-r bg-background">
          <nav className="flex-1 space-y-1 p-2">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                    isActive
                      ? "bg-[#F2542D] text-white font-medium"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
