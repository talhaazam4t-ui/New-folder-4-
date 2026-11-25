"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { getBackendUrl } from "@/lib/api";
import { getActiveTenant } from "@/lib/auth";

function getOrCreateSessionKey(): string {
  if (typeof window === "undefined") return "ssr";
  const keyName = "talox_analytics_sid";
  let sid = sessionStorage.getItem(keyName);
  if (!sid) {
    sid = `sid_${Math.random().toString(36).slice(2, 12)}`;
    sessionStorage.setItem(keyName, sid);
  }
  return sid;
}

export function AnalyticsTracker() {
  const pathname = usePathname();
  const lastTrackedRef = useRef<string>("");

  useEffect(() => {
    if (typeof window === "undefined" || !pathname) return;
    if (lastTrackedRef.current === pathname) return;
    lastTrackedRef.current = pathname;

    const tenant = getActiveTenant();
    const url = `${getBackendUrl()}/api/v1/analytics/events`;
    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      keepalive: true,
      body: JSON.stringify({
        event_name: "page_view",
        page_path: pathname,
        referrer: document.referrer ? document.referrer.slice(0, 400) : null,
        session_key: getOrCreateSessionKey(),
        tenant_id: tenant?.id || null,
      }),
    }).catch(() => {
      // Non-blocking privacy-friendly telemetry
    });
  }, [pathname]);

  return null;
}
