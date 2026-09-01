"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createFilm, saveHostToken } from "@/lib/api";

export function CreateFilmForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [hoursOpen, setHoursOpen] = useState(24);
  const [revealHours, setRevealHours] = useState(24);
  const [shotLimit, setShotLimit] = useState(8);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      // The form asks for durations because that is how hosts think about an
      // event; the API stores instants so the reveal rule stays a plain
      // comparison against the database clock.
      const now = Date.now();
      const created = await createFilm({
        title: title.trim() || "Untitled film",
        event_type: "party",
        closes_at: new Date(now + hoursOpen * 3_600_000).toISOString(),
        reveal_at: new Date(now + revealHours * 3_600_000).toISOString(),
        shot_limit: shotLimit,
        guest_cap: 5,
        ...(email.trim() ? { host_email: email.trim() } : {}),
      });

      // The only copy of this token. Losing it means losing host control, which
      // is the trade for hosts not having accounts.
      saveHostToken(created.film.code, created.host_token);
      router.push(`/f/${created.film.code}/host`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create film");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex w-full max-w-md flex-col gap-5">
      <label className="flex flex-col gap-2">
        <span className="text-sm text-zinc-400">Film name</span>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Maya and Jon's wedding"
          className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
        />
      </label>
      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-2">
          <span className="text-sm text-zinc-400">Open (hours)</span>
          <input
            type="number"
            min={1}
            max={168}
            value={hoursOpen}
            onChange={(e) => setHoursOpen(Number(e.target.value))}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
          />
        </label>
        <label className="flex flex-col gap-2">
          <span className="text-sm text-zinc-400">Reveal after (hours)</span>
          <input
            type="number"
            min={0}
            max={336}
            value={revealHours}
            onChange={(e) => setRevealHours(Number(e.target.value))}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
          />
        </label>
        <label className="flex flex-col gap-2">
          <span className="text-sm text-zinc-400">Shots per guest</span>
          <input
            type="number"
            min={1}
            max={40}
            value={shotLimit}
            onChange={(e) => setShotLimit(Number(e.target.value))}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
          />
        </label>
      </div>
      <label className="flex flex-col gap-2">
        <span className="text-sm text-zinc-400">Your email (optional)</span>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="so you can recover this film"
          className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
        />
      </label>
      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      <button
        type="submit"
        disabled={busy}
        className="rounded-full bg-white px-5 py-3 text-sm font-medium text-black disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create your film"}
      </button>
      <p className="text-xs text-zinc-500">
        Five guests are free. Add a larger room from the host page — billed on
        the web, not through the App Store. An email is how you get the host
        tools back if this browser is cleared.
      </p>
    </form>
  );
}
