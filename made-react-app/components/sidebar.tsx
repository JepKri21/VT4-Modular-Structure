"use client";
import React, { use } from "react";
import { Button } from "./ui/button";
import {
  Calendar,
  Coins,
  Factory,
  LayoutDashboard,
  LucideIcon,
  Menu,
  PackageOpen,
  Paintbrush,
  ShoppingCart,
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
        className={` cursor-pointer flex items-center ${isCollapsed ? "justify-center py-4" : "justify-start px-8  py-4"} hover:bg-blue-500 hover:text-blue-400 gap-3 transitio-colors ${isActive ? "bg-blue-400 text-black" : ""}`}
      >
        <Icon
          className={`w-6 h-6 ${isActive ? "text-white" : "text-blue-400"}`}
        />
        <span
          className={`${isCollapsed ? "hidden" : "block"} ${isActive ? "text-white font-bold" : "text-blue-400"}`}
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

  const sidebarClassNames = `fixed flex flex-col ${isSidebarCollapsed ? " w-0 md:w-16" : "w-72 md:w-64"} bg-gray-200 transition-all duration-300 overflow-hidden h-full shadow-md z-40`;

  return (
    <div className={sidebarClassNames}>
      {/* TOP LOGO */}
      <div
        className={`flex justify-between gap-3 md:justify-normal items-center pt-8 ${isSidebarCollapsed ? "px-5" : "px-8"}`}
      >
        <div>logo</div>
        <h1
          className={`${isSidebarCollapsed ? "hidden" : "block"} font-extrabold text-m text-blue-400`}
        >
          Flexible Manufacturing System
        </h1>
        <Button
          className="group px-3 py-3 rounded-full bg-gray-200 text-dark-400 hover:bg-blue-400"
          onClick={toggleSidebar}
        >
          <Menu className="w-4 h-4 transition-colors group-hover:text-white" />
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
      </div>
      {/* FOOTER */}
      <div
        className={`${isSidebarCollapsed ? "hidden" : "block"} text-center text-xs mb-10 text-gray-500`}
      >
        <p>&copy; 2026 Aalborg Universitet</p>
      </div>
    </div>
  );
};

export default Sidebar;
