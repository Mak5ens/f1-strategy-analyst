"use client";

import { useState } from "react";

/** The two motions of the site, replayed on demand: a panel entering, and a line drawn. */
export function MotionDemo({ label }: { label: string }) {
  const [run, setRun] = useState(0);
  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        onClick={() => setRun((count) => count + 1)}
        className="self-start font-semibold text-primary-text text-sm hover:underline"
      >
        {label}
      </button>
      <div key={run} className="enter rounded-xl bg-band p-4">
        <svg viewBox="0 0 400 80" aria-hidden className="block h-auto w-full max-w-xl">
          <path
            d="M0 70 L60 60 L120 62 L180 40 L240 44 L300 20 L400 10"
            fill="none"
            stroke="var(--primary)"
            strokeWidth={2.5}
            pathLength={1}
            className="draw"
          />
        </svg>
      </div>
    </div>
  );
}
