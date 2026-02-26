"use client";
import { Bell, Menu, Moon, Sun } from "lucide-react";
import { Search } from "lucide-react";
import React from "react";
import { Button } from "./ui/button";
import { useTheme } from "next-themes";
import { useAppDispatch, useAppSelector } from "@/app/redux";
import { setIsDarkMode, setIsSidebarCollapsed } from "@/state";

const Navbar = () => {
  const { theme, setTheme } = useTheme();
  const isDark = theme === "dark";
  const dispatch = useAppDispatch();
  const isSidebarCollapsed = useAppSelector(
    (state) => state.global.isSidebarCollapsed,
  );
  const isDarkMode = useAppSelector((state) => state.global.isDarkMode);

  const toggleSidebar = () => {
    dispatch(setIsSidebarCollapsed(!isSidebarCollapsed));
  };

  const toggleDarkMode = () => {
    dispatch(setIsDarkMode(!isDarkMode));
  };

  return (
    <div className="flex justify-between items-center mb-7 w-full">
      {/* LEFT SIDE */}
      <div className="flex justify-between items-center gap-5">
        <Button
          className="group px-3 py-3 rounded-full bg-muted text-foreground hover:bg-primary"
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
        <div className="hidden md:flex justify-between items-center gap-5">
          {/* WILL BE USED IN THE FUTURE FOR DARK MODE TOGGLE */}
          {/* <Button
            className="group cursor-pointer px-3 py-3 rounded-full bg-muted text-foreground hover:bg-primary hover:text-primary-foreground transition-colors"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Sun className="transition-colors" />
          </Button> */}
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
        <div className="relative">
          <Bell className="cursor-pointer" size={24} />
          <span className="absolute -top-2 -right-1 inline-flex items-center justify-center px-[0.2rem] py-[0.02rem] text-xs font-semibold bg-primary text-background rounded-full">
            3
          </span>
        </div>
        <div className="w-8 h-8 rounded-full bg-secondary"></div>
      </div>
    </div>
  );
};

export default Navbar;
