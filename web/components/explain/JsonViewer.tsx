"use client";

import { useState } from "react";

export function JsonViewer({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  const text = JSON.stringify(value, null, 2);
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="text-sm underline"
      >
        {open ? "Hide raw data" : "Show raw data"}
      </button>
      {open ? (
        <div className="mt-2">
          <pre className="max-h-80 overflow-auto rounded bg-slate-100 p-2 text-xs dark:bg-slate-800">
            {text}
          </pre>
          <button
            type="button"
            className="mt-1 text-sm underline"
            onClick={() => void navigator.clipboard?.writeText(text)}
          >
            Copy raw data
          </button>
        </div>
      ) : null}
    </div>
  );
}
