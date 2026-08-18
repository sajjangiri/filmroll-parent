"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { API_URL, ApiError, getFilm, loadHostToken, revealFilm } from "@/lib/api";
import type { FilmPublic } from "@/lib/types";

const neverChanges = () => () => {};
const readOrigin = () => window.location.origin;
const originOnServer = () => "";

export function HostDashboard({ code }: { code: string }) {
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [revealing, setRevealing] = useState(false);

  const origin = useSyncExternalStore(neverChanges, readOrigin, originOnServer);
  const joinUrl = film?.join_url || (origin ? `${origin}/f/${code}` : "");
  const qrSrc = `${API_URL}/v1/films/${code}/qr.svg`;

  useEffect(() => {
    getFilm(code)
      .then(setFilm)
      .catch(() => setError("Film not found"));
  }, [code]);

  async function reveal() {
    const hostToken = loadHostToken(code);
    if (!hostToken) {
      setError("Host key missing. Open this from the device that created the film.");
      return;
    }
    setError("");
    setRevealing(true);
    try {
      setFilm(await revealFilm(code, hostToken));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "That host key is not valid for this film."
          : "Could not develop the film.",
      );
    } finally {
      setRevealing(false);
    }
  }

  async function copy() {
    if (!joinUrl) return;
    await navigator.clipboard.writeText(joinUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  if (error && !film) return <p className="text-red-400">{error}</p>;
  if (!film) return <p className="text-zinc-400">Loading host tools…</p>;

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-8">
      <header className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Host</p>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.guest_count}/{film.guest_cap} guests · {film.shot_limit} per camera
        </p>
      </header>

      <section className="flex flex-col items-center gap-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
        {/* Served by our API as SVG, not by a third-party image endpoint.
            The join URL names a private event. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={qrSrc} alt="Join QR code" width={240} height={240} className="rounded-lg bg-white p-2" />
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
        <p>Closes {new Date(film.closes_at).toLocaleString()}</p>
        <p>
          {film.is_developed
            ? "Gallery is open."
            : `Develops ${new Date(film.reveal_at).toLocaleString()}`}
        </p>
        {error ? <p className="text-red-400">{error}</p> : null}
        <div className="flex gap-3">
          {!film.is_developed ? (
            <button
              type="button"
              onClick={reveal}
              disabled={revealing}
              className="rounded-full border border-zinc-600 px-5 py-2 text-sm disabled:opacity-40"
            >
              {revealing ? "Developing…" : "Develop now"}
            </button>
          ) : (
            <a
              href={`/f/${code}/gallery`}
              className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
            >
              Open gallery
            </a>
          )}
          <a
            href={`/f/${code}`}
            className="rounded-full px-5 py-2 text-sm text-zinc-400"
          >
            Open guest camera
          </a>
        </div>
      </section>
    </div>
  );
}
