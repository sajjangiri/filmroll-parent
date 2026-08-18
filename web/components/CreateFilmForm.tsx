"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function CreateFilmForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [hoursOpen, setHoursOpen] = useState(24);
  const [revealHours, setRevealHours] = useState(24);
  const [shotLimit, setShotLimit] = useState(8);
  const [guestCap, setGuestCap] = useState(5);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/films", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          hoursOpen,
          revealHours,
          shotLimit,
          guestCap,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not create film");
      const { film, hostSecret } = data as {
        film: { code: string };
        hostSecret: string;
      };
      window.localStorage.setItem(`filmroll-host-${film.code}`, hostSecret);
      router.push(`/f/${film.code}/host`);
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
        <label className="flex flex-col gap-2">
          <span className="text-sm text-zinc-400">Guest cap</span>
          <input
            type="number"
            min={1}
            max={200}
            value={guestCap}
            onChange={(e) => setGuestCap(Number(e.target.value))}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
          />
        </label>
      </div>
      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      <button
        type="submit"
        disabled={busy}
        className="rounded-full bg-white px-5 py-3 text-sm font-medium text-black disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create your film"}
      </button>
      <p className="text-xs text-zinc-500">
        Free while we clone the Once loop. Guest cap is not billed yet.
      </p>
    </form>
  );
}
