"use client";
import AlertPanel from "../AlertPanel";
import PageHead from "../PageHead";

export default function Page() {
  return (
    <>
      <PageHead title="Alerts"
        sub="CAP 1.2 documents carrying Telugu, Hindi and English in one message" />
      <AlertPanel />
    </>
  );
}
