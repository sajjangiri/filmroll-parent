"use client";

import { useCallback, useEffect, useState } from "react";
import { Camera } from "@/components/guest/Camera";
import { InstallHint } from "@/components/guest/InstallHint";
import {
  ApiError,
  clearGuestToken,
  getFilm,
  joinFilm,
  loadGuestToken,
  saveGuestToken,
} from "@/lib/api";
import type { FilmPublic } from "@/lib/types";

export function GuestApp({ code }: { code: string }) {
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const loaded = await getFilm(code);
        if (cancelled) return;
        setFilm(loaded);
        // A token from a previous visit means this device already has a camera.
        setToken(loadGuestToken(code));
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError && err.status === 404
              ? "That film code does not exist."
              : "Could not reach the film.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code]);

  async function onJoin(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setJoining(true);
    try {
      const joined = await joinFilm(code, name.trim());
      saveGuestToken(code, joined.guest_token);
      setToken(joined.guest_token);
      setRemaining(joined.shots_remaining);
      setFilm(await getFilm(code));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "This film is full."
          : err instanceof ApiError && err.status === 410
            ? "This film has closed."
            : err instanceof ApiError && err.status === 429
              ? "Too many attempts. Wait a moment and try again."
              : "Could not join this film.",
      );
    } finally {
      setJoining(false);
    }
  }

  // A token can outlive its film, or be rejected after a host resets things.
  const onUnauthorized = useCallback(() => {
    clearGuestToken(code);
    setToken(null);
    setError("Your camera expired. Join again to keep shooting.");
  }, [code]);

  if (loading) {
    return <p className="text-zinc-400">Loading film…</p>;
  }
  if (!film) {
    return <p className="text-red-400">{error || "Film not found"}</p>;
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6">
      <header className="flex flex-col gap-1">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Filmroll</p>
        <h1 className="font-serif text-3xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.guest_count}/{film.guest_cap} guests ·{" "}
          {film.unlimited_shots ? "unlimited shots" : `${film.shot_limit} shots each`}
        </p>
        <InstallHint />
      </header>

      {film.is_developed ? (
        <a
          href={`/f/${code}/gallery`}
          className="rounded-full bg-white px-5 py-3 text-center text-sm font-medium text-black"
        >
          Film has developed — view gallery
        </a>
      ) : null}

      {!token ? (
        <form onSubmit={onJoin} className="flex flex-col gap-3">
          <p className="text-sm text-zinc-400">
            Enter your name to pick up a camera. No account needed.
          </p>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            required
            maxLength={80}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-zinc-100 outline-none focus:border-zinc-500"
          />
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          <button
            type="submit"
            disabled={film.is_closed || joining}
            className="rounded-full bg-white px-5 py-3 text-sm font-medium text-black disabled:opacity-40"
          >
            {film.is_closed
              ? "This film is closed"
              : joining
                ? "Joining…"
                : "Join the film"}
          </button>
        </form>
      ) : film.is_closed ? (
        <p className="text-zinc-400">
          Shooting has ended. Come back when the film develops.
        </p>
      ) : (
        <Camera
          code={code}
          token={token}
          film={film}
          remaining={remaining}
          onRemainingChange={setRemaining}
          onUnauthorized={onUnauthorized}
        />
      )}
    </div>
  );
}
