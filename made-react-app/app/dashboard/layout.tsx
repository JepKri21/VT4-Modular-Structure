import React from "react";

const layout = ({ children }: { children: React.ReactNode }) => {
  return (
    <div>
      <p>Dashboard Layout</p>
      {children}
      <p>Dashboard Footer</p>
    </div>
  );
};

export default layout;
