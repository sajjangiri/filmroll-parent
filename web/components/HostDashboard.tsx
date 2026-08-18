"use client";

import { useEffect, useState } from "react";
import type { PublicFilm } from "@/lib/types";

export function HostDashboard({ code }: { code: string }) {
  const [film, setFilm] = useState<PublicFilm | null>(null);
  const [joinUrl, setJoinUrl] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setJoinUrl(`${window.location.origin}/f/${code}`);
    fetch(`/api/films/${code}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.film) setFilm(data.film);
        else setError(data.error || "Film not found");
      });
  }, [code]);

  async function reveal() {
    const hostSecret = window.localStorage.getItem(`filmroll-host-${code}`);
    if (!hostSecret) {
      setError("Host key missing. Create the film on this device.");
      return;
    }
    const res = await fetch(`/api/films/${code}/reveal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hostSecret }),
    });
    const data = await res.json();
    if (!res.ok) {
      setError(data.error || "Could not reveal");
      return;
    }
    setFilm(data.film);
  }

  async function copy() {
    await navigator.clipboard.writeText(joinUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (error && !film) return <p className="text-red-400">{error}</p>;
  if (!film) return <p className="text-zinc-400">Loading host tools…</p>;

  const developed = film.revealed || Date.now() >= Date.parse(film.revealAt);
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(joinUrl)}`;

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-8">
      <header className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">
          Host
        </p>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.guests.length}/{film.guestCap} guests · {film.shots.length}{" "}
          shots · {film.shotLimit} per camera
        </p>
      </header>

      <section className="flex flex-col items-center gap-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={qrSrc} alt="Join QR code" width={240} height={240} />
        <p className="break-all text-center text-sm text-zinc-400">{joinUrl}</p>
        <button
          type="button"
          onClick={copy}
          className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
        >
          {copied ? "Copied" : "Copy join link"}
        </button>
      </section>

      <section className="flex flex-col gap-3 text-sm text-zinc-300">
        <p>Closes {new Date(film.closesAt).toLocaleString()}</p>
        <p>
          {developed
            ? "Gallery is open."
            : `Develops ${new Date(film.revealAt).toLocaleString()}`}
        </p>
        {error ? <p className="text-red-400">{error}</p> : null}
        <div className="flex gap-3">
          {!developed ? (
            <button
              type="button"
              onClick={reveal}
              className="rounded-full border border-zinc-600 px-5 py-2 text-sm"
            >
              Develop now
            </button>
          ) : (
            <a
              href={`/f/${code}/gallery`}
              className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
            >
              Open gallery
            </a>
          )}
          <a href={`/f/${code}`} className="rounded-full px-5 py-2 text-sm text-zinc-400">
            Open guest camera
          </a>
        </div>
      </section>
    </div>
  );
}
