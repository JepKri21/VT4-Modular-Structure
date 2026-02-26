"use client";
import React, { use } from "react";
import { Button } from "./ui/button";
import {
  Calendar,
  Cog,
  Coins,
  Factory,
  LayoutDashboard,
  LucideIcon,
  Menu,
  PackageOpen,
  Paintbrush,
  ShoppingCart,
  Store,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/app/redux";
import { setIsSidebarCollapsed } from "@/state";
import { usePathname } from "next/navigation";
import Link from "next/link";
import layout from "@/app/dashboard/layout";

interface sidebarLinkProps {
  href: string;
  icon: LucideIcon;
  label: string;
  isCollapsed: boolean;
}

const SidebarLink = ({
  href,
  icon: Icon,
  label,
  isCollapsed,
}: sidebarLinkProps) => {
  const pathname = usePathname();
  const isActive =
    pathname === href || (pathname === "/" && href === "/dashboard");

  return (
    <Link href={href}>
      <div
        className={` cursor-pointer flex items-center ${isCollapsed ? "justify-center py-4" : "justify-start px-8  py-4"} hover:bg-card hover:text-primary gap-3 transition-colors ${isActive ? "bg-primary text-background" : ""}`}
      >
        <Icon
          className={`w-6 h-6 ${isActive ? "text-background" : "text-primary"}`}
        />
        <span
          className={`${isCollapsed ? "hidden" : "block"} ${isActive ? "text-background font-bold" : "text-primary"}`}
        >
          {label}
        </span>
      </div>
    </Link>
  );
};

const Sidebar = () => {
  const dispatch = useAppDispatch();
  const isSidebarCollapsed = useAppSelector(
    (state) => state.global.isSidebarCollapsed,
  );

  const toggleSidebar = () => {
    dispatch(setIsSidebarCollapsed(!isSidebarCollapsed));
  };

  // const sidebarClassNames = `fixed flex flex-col ${isSidebarCollapsed ? " w-0 md:w-16" : "w-72 md:w-64"} bg-muted transition-all duration-300 overflow-hidden h-full shadow-md z-40`;
  const sidebarClassNames = `
  fixed
  flex
  flex-col
  ${isSidebarCollapsed ? "w-0 md:w-16" : "w-72 md:w-64"}
  bg-muted
  transition-all
  duration-300
  h-screen
  overflow-y-auto
  overflow-x-hidden
  hide-scrollbar
  shadow-md
  z-40
`;
  return (
    <div className={sidebarClassNames}>
      {/* TOP LOGO */}
      <div
        className={`flex justify-between gap-3 md:justify-normal items-center pt-8 ${isSidebarCollapsed ? "px-5" : "px-8"}`}
      >
        <div>logo</div>
        <h1
          className={`${isSidebarCollapsed ? "hidden" : "block"} font-extrabold text-m text-primary`}
        >
          Flexible Manufacturing System
        </h1>
        <Button
          className="group px-3 py-3 rounded-full bg-muted text-foreground hover:bg-primary"
          onClick={toggleSidebar}
        >
          <Menu className="w-4 h-4 transition-colors group-hover:text-background" />
        </Button>
      </div>
      {/* NAVIGATION */}

      <div className="flex-grow mt-8">
        <SidebarLink
          href="/dashboard"
          icon={LayoutDashboard}
          label="Dashboard"
          isCollapsed={isSidebarCollapsed}
        />

        {/* MES */}
        <div
          className={` flex items-center gap-3 transition-colors rounded-md px-4 py-4 mt-4 ${isSidebarCollapsed ? "hidden" : "block"}`}
        >
          <h3 className="text-xs text-primary ">MES & ERP</h3>
        </div>
        <SidebarLink
          href="/assets"
          icon={Wrench}
          label="Assets"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/production-monitoring"
          icon={Factory}
          label="Production Monitoring"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/maintainance"
          icon={Paintbrush}
          label="Maintenance"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/alarms"
          icon={TriangleAlert}
          label="Alarms"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/inventory-management"
          icon={PackageOpen}
          label="Inventory Management"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/expenses"
          icon={Coins}
          label="Expenses"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/scheduling"
          icon={Calendar}
          label="Scheduling"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/orders"
          icon={ShoppingCart}
          label="Orders"
          isCollapsed={isSidebarCollapsed}
        />
        {/* ADMIN CONTROL */}
        <div
          className={` flex items-center gap-3 transition-colors rounded-md px-4 py-4 mt-4 ${isSidebarCollapsed ? "hidden" : "block"}`}
        >
          <h3 className="text-xs text-primary ">ADMIN CONTROL</h3>
        </div>
        <SidebarLink
          href="/virtual-store"
          icon={Store}
          label="Virtual Store"
          isCollapsed={isSidebarCollapsed}
        />
        <SidebarLink
          href="/configurator"
          icon={Cog}
          label="Configurator"
          isCollapsed={isSidebarCollapsed}
        />
      </div>
      {/* FOOTER */}
      <div
        className={`${isSidebarCollapsed ? "hidden" : "block"} text-center text-xs mask-b-to-10 text-gray-500`}
      >
        <p>&copy; 2026 Aalborg Universitet</p>
      </div>
    </div>
  );
};

export default Sidebar;
