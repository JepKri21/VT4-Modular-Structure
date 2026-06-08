"use client";
import { Bell, Menu, Moon, Sun } from "lucide-react";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "./ui/button";
import { useTheme } from "next-themes";
import { useAppDispatch, useAppSelector } from "@/app/redux";
import { setIsSidebarCollapsed } from "@/state";
import NotificationSidePanel from "./NotificationSidePanel";

const ALARM_POLL_INTERVAL_MS = 3000;

const Navbar = () => {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark";
  const dispatch = useAppDispatch();
  const isSidebarCollapsed = useAppSelector(
    (state) => state.global.isSidebarCollapsed,
  );

  const [activeAlarms, setActiveAlarms] = useState<number>(0);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const fetchSummary = async () => {
      try {
        const res = await fetch("/api/alarms/summary", { cache: "no-store" });
        const data = await res.json();
        if (!cancelled) setActiveAlarms(Number(data.active ?? 0));
      } catch {
        // Swallow transient errors — the next tick will retry.
      }
    };
    fetchSummary();
    const id = setInterval(fetchSummary, ALARM_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const toggleSidebar = () => {
    dispatch(setIsSidebarCollapsed(!isSidebarCollapsed));
  };

  return (
    <div className="flex justify-between items-center mb-7 w-full">
      {/* LEFT SIDE */}
      <div className="flex justify-between items-center gap-5">
        <Button
          className="group cursor-pointer px-1 py-1 rounded-full bg-muted text-foreground hover:bg-primary"
          onClick={toggleSidebar}
        >
          <Menu className="w-4 h-4 transition-colors group-hover:text-background" />
        </Button>
      </div>
      <div className="relative">
        <input
          type="text"
          placeholder="Search..."
          className="pl-10 pr-4 py-2 w-40 md:w-50 rounded-full bg-muted focus:outline-none focus:ring-1 focus:ring-primary focus:border-transparent"
        />
        <Search className="w-4 h-4 text-foreground absolute left-3 top-1/2 transform -translate-y-1/2" />
      </div>

      {/* COMPANY NAME */}
      <h1 className="text-2xl md:text-3xl font-bold text-primary">
        AAU SMARTLAB
      </h1>
      {/* RIGHT SIDE */}
      <div className="flex justify-between items-center gap-5">
        {/* DARK MODE */}
        <div className="hidden md:flex justify-between items-center gap-5">
          <Button
            className="group cursor-pointer px-3 py-3 rounded-full bg-muted text-foreground hover:bg-primary hover:text-primary-foreground transition-colors"
            variant="secondary"
            size="icon"
            onClick={() => setTheme(isDark ? "light" : "dark")}
          >
            {isDark ? (
              <Sun className="transition-colors" size={18} />
            ) : (
              <Moon size={18} />
            )}
          </Button>
        </div>
        {/* NOTIFICATIONS */}
        <div className="hidden md:flex justify-between items-center gap-5">
          <Button
            // `relative` is what anchors the unread-count badge below.
            // Without it, the badge falls back to the nearest ancestor
            // with position:relative and ends up in the wrong place.
            className="group relative cursor-pointer px-3 py-3 rounded-full bg-muted text-foreground hover:bg-primary hover:text-primary-foreground transition-colors"
            variant="secondary"
            size="icon"
            onClick={() => setNotificationsOpen(true)}
            aria-label="Notifications"
          >
            <Bell className="transition-colors" size={18} />
            {activeAlarms > 0 && (
              <span className="absolute -top-1 -right-1 inline-flex items-center justify-center min-w-4.5 h-4.5 px-1 text-[10px] font-semibold bg-primary text-background rounded-full">
                {activeAlarms}
              </span>
            )}
          </Button>
        </div>
        <div className="w-8 h-8 rounded-full bg-secondary"></div>
      </div>

      <NotificationSidePanel
        open={notificationsOpen}
        onClose={() => setNotificationsOpen(false)}
      />
    </div>
  );
};

export default Navbar;
