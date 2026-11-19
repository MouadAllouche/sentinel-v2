"use client";

import { useState } from "react";

import { Button } from "@/components/ui/primitives";
import type { Role } from "@/lib/auth";
import { sanitizeMarkdown } from "@/lib/incident/helpers";

export function NotesPanel({
  notes,
  currentRole,
  onAdd,
}: {
  notes: Array<{ id: number; author: string; body: string; created_at: string }>;
  currentRole: Role;
  onAdd: (body: string) => void;
}) {
  const [body, setBody] = useState("");
  return (
    <div className="space-y-3">
      <ul className="space-y-2" aria-label="Analyst notes">
        {notes.length === 0 ? <li className="text-sm text-slate-500">No notes yet.</li> : null}
        {notes.map((note) => (
          <li key={note.id} className="rounded border border-slate-200 p-2 text-sm dark:border-slate-700">
            <p className="text-xs text-slate-500">{note.author} · {note.created_at}</p>
            {/* Sanitised by sanitizeMarkdown: no raw HTML is ever injected. */}
            <div dangerouslySetInnerHTML={{ __html: sanitizeMarkdown(note.body) }} />
          </li>
        ))}
      </ul>
      {currentRole === "admin" ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!body.trim()) return;
            onAdd(body);
            setBody("");
          }}
        >
          <label className="block text-sm" htmlFor="new-note">
            Add a note
            <textarea
              id="new-note"
              className="mt-1 w-full rounded border border-slate-300 p-2 dark:border-slate-600 dark:bg-slate-800"
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
          </label>
          <Button type="submit" className="mt-2">Add note</Button>
        </form>
      ) : null}
    </div>
  );
}
