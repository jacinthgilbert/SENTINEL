"use client";

import { useEffect, useState } from "react";

/** Shown once per browser session, not on every navigation. */
export default function Splash() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem("sentinel:splash") === "done") return;
      sessionStorage.setItem("sentinel:splash", "done");
    } catch {
      /* private mode — show it, harmless */
    }
    setShow(true);
    const t = setTimeout(() => setShow(false), 2600);
    return () => clearTimeout(t);
  }, []);

  if (!show) return null;
  return (
    <div className="splash" aria-hidden>
      <div className="splash-inner">
        <h1>SENTINEL</h1>
        <div className="splash-rule" />
        <p>Flood early warning · Visakhapatnam</p>
      </div>
    </div>
  );
}
