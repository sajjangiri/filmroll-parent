"use client";

import { useEffect, useState } from "react";
import { Camera } from "@/components/Camera";
import type { Guest, PublicFilm } from "@/lib/types";

const guestKey = (code: string) => `filmroll-guest-${code}`;

export function GuestApp({ code }: { code: string }) {
  const [film, setFilm] = useState<PublicFilm | null>(null);
  const [guest, setGuest] = useState<Guest | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await fetch(`/api/films/${code}`);
      const data = await res.json();
      if (cancelled) return;
      if (!res.ok) {
        setError(data.error || "Film not found");
        setLoading(false);
        return;
      }
      setFilm(data.film);
      const savedId = window.localStorage.getItem(guestKey(code));
      if (savedId) {
        const join = await fetch(`/api/films/${code}/join`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ guestId: savedId }),
        });
        const joinData = await join.json();
        if (join.ok) {
          setGuest(joinData.guest);
          setFilm(joinData.film);
        }
      }
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [code]);

  async function join(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    const res = await fetch(`/api/films/${code}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.error || "Could not join");
      return;
    }
    window.localStorage.setItem(guestKey(code), data.guest.id);
    setGuest(data.guest);
    setFilm(data.film);
  }

  if (loading) {
    return <p className="text-zinc-400">Loading film…</p>;
  }
  if (!film) {
    return <p className="text-red-400">{error || "Film not found"}</p>;
  }

  const closed = Date.now() > Date.parse(film.closesAt);
  const developed = film.revealed || Date.now() >= Date.parse(film.revealAt);

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6">
      <header className="flex flex-col gap-1">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
          Filmroll
        </p>
        <h1 className="font-serif text-3xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.guests.length}/{film.guestCap} guests · {film.shotLimit} shots
          each
        </p>
      </header>

      {developed ? (
        <a
          href={`/f/${code}/gallery`}
          className="rounded-full bg-white px-5 py-3 text-center text-sm font-medium text-black"
        >
          Film has developed — view gallery
        </a>
      ) : null}

      {!guest ? (
        <form onSubmit={join} className="flex flex-col gap-3">
          <p className="text-sm text-zinc-400">
            Enter your name to pick up a camera. No account needed.
          </p>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            required
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
          />
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          <button
            type="submit"
            disabled={closed}
            className="rounded-full bg-white px-5 py-3 text-sm font-medium text-black disabled:opacity-40"
          >
            {closed ? "This film is closed" : "Join the film"}
          </button>
        </form>
      ) : closed ? (
        <p className="text-zinc-400">
          Shooting has ended. Come back when the film develops.
        </p>
      ) : (
        <Camera
          code={code}
          film={film}
          guest={guest}
          onUpdate={(nextFilm, nextGuest) => {
            setFilm(nextFilm);
            setGuest(nextGuest);
          }}
        />
      )}
    </div>
  );
}
