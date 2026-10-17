"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Render the page again every few seconds, while the agent works on a request opened elsewhere. */
export function AutoRefresh({ seconds = 5 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
