import { useState } from "react";
import { NavLink, Link, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  Megaphone,
  Phone,
  Users,
  ShieldOff,
  LogOut,
  Menu,
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

function NavItems({ onNavClick }: { onNavClick?: () => void }) {
  const { logout } = useAuth();
  return (
    <>
      <nav className="flex-1 space-y-1 p-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavClick}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-[7px] px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-brand-orange text-white font-semibold"
                  : "text-brand-grey-dark hover:bg-page-bg"
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      {/* Pinned sidebar footer */}
      <div className="p-3 border-t border-brand-border">
        <SidebarFooter />
        <button
          onClick={logout}
          className="mt-1 flex items-center gap-1.5 text-xs text-brand-grey-dark hover:text-brand-black transition-colors"
        >
          <LogOut className="h-3 w-3" />
          Logout
        </button>
      </div>
    </>
  );
}

function SidebarFooter() {
  const { user } = useAuth();
  return (
    <p className="text-xs text-brand-grey-dark truncate">{user?.email}</p>
  );
}

function AvatarChip() {
  const { user } = useAuth();
  const initial = user?.name?.[0]?.toUpperCase() ?? "?";
  return (
    <div className="flex items-center gap-2 cursor-default select-none">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-gum text-white text-xs font-semibold">
        {initial}
      </div>
      <span className="text-sm text-brand-grey-dark hidden md:inline">{user?.name}</span>
    </div>
  );
}

export default function DashboardShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* Full-width top bar + powerlines */}
      <div className="flex flex-col bg-white">
        {/* Desktop header */}
        <div className="hidden md:flex h-[52px]">
          {/* Wordmark zone — matches sidebar width */}
          <div className="flex w-[220px] items-center px-4 border-r border-brand-border">
            <Link
              to="/dashboard"
              className="text-base font-black tracking-[-0.04em] uppercase text-brand-black"
            >
              POWERLINE
            </Link>
          </div>
          {/* Right zone */}
          <div className="flex flex-1 items-center justify-end px-6">
            <AvatarChip />
          </div>
        </div>

        {/* Mobile header */}
        <div className="flex md:hidden h-12 items-center px-4 justify-between">
          <button
            onClick={() => setDrawerOpen(true)}
            className="text-brand-grey-dark p-1"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <Link
            to="/dashboard"
            className="text-base font-black tracking-[-0.04em] uppercase text-brand-black"
          >
            POWERLINE
          </Link>
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-gum text-white text-xs font-semibold">
            <AvatarInitial />
          </div>
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
            <path d="M 0,22 Q 720,2 1440,18" stroke="#6b7280" strokeWidth="1.5" />
            <path d="M 0,8 Q 720,28 1440,12" stroke="#6b7280" strokeWidth="1.5" />
            <path d="M 0,15 Q 600,6 1440,24" stroke="#6b7280" strokeWidth="1.5" />
          </svg>
        </div>
      </div>

      {/* Content area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Desktop Sidebar */}
        <aside className="hidden md:flex w-[220px] flex-col border-r border-brand-border bg-white">
          <NavItems />
        </aside>

        {/* Mobile Drawer */}
        <div
          className={`fixed inset-0 z-40 bg-black/20 transition-opacity duration-200 md:hidden ${
            drawerOpen ? "opacity-100" : "opacity-0 pointer-events-none"
          }`}
          onClick={() => setDrawerOpen(false)}
        />
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-50 w-[220px] bg-white flex flex-col transition-transform duration-[280ms] ease-[cubic-bezier(0.4,0,0.2,1)] md:hidden",
            drawerOpen ? "translate-x-0" : "-translate-x-full"
          )}
        >
          <NavItems onNavClick={() => setDrawerOpen(false)} />
        </aside>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-page-bg p-4 md:p-7">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function AvatarInitial() {
  const { user } = useAuth();
  return <>{user?.name?.[0]?.toUpperCase() ?? "?"}</>;
}
