"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import Splash from "./Splash";

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  // Remember the sidebar state per viewer; harmless if storage is unavailable.
  useEffect(() => {
    try { setCollapsed(localStorage.getItem("sentinel:nav") === "collapsed"); } catch {}
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem("sentinel:nav", next ? "collapsed" : "open"); } catch {}
      return next;
    });
  };

  return (
    <>
      <Splash />
      <div className={`shell${collapsed ? " collapsed" : ""}`}>
        <Sidebar collapsed={collapsed} onToggle={toggle} />
        <div className="content">
          {/* key on the path so each navigation replays the enter animation */}
          <div className="page page-enter" key={path}>{children}</div>
        </div>
      </div>
    </>
  );
}
