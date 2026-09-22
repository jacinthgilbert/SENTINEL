"use client";
import OfflinePanel from "../OfflinePanel";
import PageHead from "../PageHead";

export default function Page() {
  return (
    <>
      <PageHead title="Offline"
        sub="Cached map, last-known risk, and reports queued until the network returns" />
      <OfflinePanel />
    </>
  );
}
