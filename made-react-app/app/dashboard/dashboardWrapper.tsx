"use client";
import React, { useEffect } from "react";
import Navbar from "@/components/navbar";
import Sidebar from "@/components/sidebar";
import StoreProvider, { useAppSelector } from "../redux";

const DashboardLayout = ({ children }: { children: React.ReactNode }) => {
  const isSidebarCollapsed = useAppSelector(
    (state) => state.global.isSidebarCollapsed,
  );

  return (
    <div className="flex bg-background text-foreground min-h-screen w-full">
      <Sidebar />
      <main
        className={`flex flex-col w-full h-full py-7 px-9 bg-background ${
          isSidebarCollapsed ? "md:pl-24" : "md:pl-72"
        }`}
      >
        <Navbar />
        {children}
      </main>
    </div>
  );
};

const DashboardWrapper = ({ children }: { children: React.ReactNode }) => {
  return (
    <StoreProvider>
      <DashboardLayout>{children}</DashboardLayout>
    </StoreProvider>
  );
};

export default DashboardWrapper;
