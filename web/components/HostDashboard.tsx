"use client";

import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import {
  API_URL,
  ApiError,
  cardsPdfUrl,
  getExport,
  getFilm,
  getReview,
  hideShot,
  loadHostToken,
  revealFilm,
  startExport,
  unhideShot,
  updateFilm,
} from "@/lib/api";
import type { ExportResponse, FilmPublic, ReviewPhoto } from "@/lib/types";

const neverChanges = () => () => {};
const readOrigin = () => window.location.origin;
const originOnServer = () => "";

export function HostDashboard({ code }: { code: string }) {
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [photos, setPhotos] = useState<ReviewPhoto[]>([]);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [revealing, setRevealing] = useState(false);
  const [exportState, setExportState] = useState<ExportResponse | null>(null);
  const [guestCap, setGuestCap] = useState(25);
  const [shotLimit, setShotLimit] = useState(8);
  const [hasHostKey, setHasHostKey] = useState(false);

  const origin = useSyncExternalStore(neverChanges, readOrigin, originOnServer);
  const joinUrl = film?.join_url || (origin ? `${origin}/f/${code}` : "");
  const qrSrc = `${API_URL}/v1/films/${code}/qr.svg`;

  const refresh = useCallback(async () => {
    try {
      const loaded = await getFilm(code);
      setFilm(loaded);
      setGuestCap(loaded.guest_cap);
      setShotLimit(loaded.shot_limit);
    } catch {
      setError("Film not found");
      return;
    }
    const token = loadHostToken(code);
    setHasHostKey(Boolean(token));
    if (!token) return;
    try {
      const review = await getReview(code, token);
      setPhotos(review.photos);
      const exp = await getExport(code, token);
      setExportState(exp);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError("This device does not have the host key for this film.");
      }
    }
  }, [code]);

  useEffect(() => {
    const id = window.setInterval(() => {
      void refresh();
    }, 8000);
    const first = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(first);
    };
  }, [refresh]);

  async function reveal() {
    const token = loadHostToken(code);
    if (!token) {
      setError("Host key missing. Open this from the device that created the film.");
      return;
    }
    setError("");
    setRevealing(true);
    try {
      setFilm(await revealFilm(code, token));
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

  async function toggleHidden(photo: ReviewPhoto) {
    const token = loadHostToken(code);
    if (!token) return;
    setPhotos((current) =>
      current.map((item) =>
        item.shot_id === photo.shot_id ? { ...item, hidden: !item.hidden } : item,
      ),
    );
    try {
      if (photo.hidden) await unhideShot(code, photo.shot_id, token);
      else await hideShot(code, photo.shot_id, token);
    } catch {
      setPhotos((current) =>
        current.map((item) =>
          item.shot_id === photo.shot_id ? { ...item, hidden: photo.hidden } : item,
        ),
      );
      setError("Could not update that photo.");
    }
  }

  async function saveCaps() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      setFilm(await updateFilm(code, token, { guest_cap: guestCap, shot_limit: shotLimit }));
      setError("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "That cap is below people who already joined."
          : "Could not update the film.",
      );
    }
  }

  async function requestZip() {
    const token = loadHostToken(code);
    if (!token) return;
    try {
      setExportState(await startExport(code, token));
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        const next = await getExport(code, token);
        setExportState(next);
        if (next.status === "ready" && next.download_url) {
          window.location.href = next.download_url;
          return;
        }
        if (next.status === "failed") {
          setError("The ZIP could not be built.");
          return;
        }
      }
    } catch {
      setError("Could not start the download.");
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

  const hiddenCount = photos.filter((photo) => photo.hidden).length;
  const waiting = exportState?.status === "pending";

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
      <header className="flex flex-col gap-2">
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Host</p>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.guest_count}/{film.guest_cap} guests · {film.shot_count} shots ·{" "}
          {film.shot_limit} per camera
          {hiddenCount ? ` · ${hiddenCount} hidden` : ""}
        </p>
      </header>

      <section className="flex flex-col items-center gap-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-6">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={qrSrc}
          alt="Join QR code"
          width={240}
          height={240}
          className="rounded-lg bg-white p-2"
        />
        <p className="break-all text-center text-sm text-zinc-400">{joinUrl}</p>
        <div className="flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={copy}
            className="rounded-full bg-white px-5 py-2 text-sm font-medium text-black"
          >
            {copied ? "Copied" : "Copy join link"}
          </button>
          <a
            href={cardsPdfUrl(code)}
            className="rounded-full border border-zinc-600 px-5 py-2 text-sm"
          >
            Download table cards (PDF)
          </a>
          <a href={`/f/${code}/print`} className="rounded-full px-5 py-2 text-sm text-zinc-400">
            Print from browser
          </a>
        </div>
      </section>

      <section className="flex flex-col gap-3 text-sm text-zinc-300">
        <p>Closes {new Date(film.closes_at).toLocaleString()}</p>
        <p>
          {film.is_developed
            ? "Gallery is open."
            : `Develops ${new Date(film.reveal_at).toLocaleString()}`}
        </p>
        {error ? <p className="text-red-400">{error}</p> : null}
        <div className="flex flex-wrap gap-3">
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
          <button
            type="button"
            onClick={requestZip}
            disabled={waiting || !hasHostKey}
            className="rounded-full border border-zinc-600 px-5 py-2 text-sm disabled:opacity-40"
          >
            {waiting
              ? "Building ZIP…"
              : exportState?.status === "ready"
                ? "Download originals ZIP"
                : "Export originals"}
          </button>
          <a href={`/f/${code}`} className="rounded-full px-5 py-2 text-sm text-zinc-400">
            Open guest camera
          </a>
        </div>
      </section>

      {hasHostKey ? (
        <section className="flex flex-col gap-3 rounded-2xl border border-zinc-800 p-4">
          <p className="text-sm text-zinc-400">Raise capacity mid-event</p>
          <div className="grid grid-cols-2 gap-3">
            <label className="flex flex-col gap-1 text-sm">
              Guest cap
              <input
                type="number"
                min={film.guest_count}
                max={1000}
                value={guestCap}
                onChange={(e) => setGuestCap(Number(e.target.value))}
                className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Shots per guest
              <input
                type="number"
                min={1}
                max={500}
                value={shotLimit}
                onChange={(e) => setShotLimit(Number(e.target.value))}
                className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2"
              />
            </label>
          </div>
          <button
            type="button"
            onClick={saveCaps}
            className="self-start rounded-full border border-zinc-600 px-5 py-2 text-sm"
          >
            Save
          </button>
        </section>
      ) : (
        <p className="text-sm text-zinc-500">
          Moderation and export need the host key from the device that created
          this film.
        </p>
      )}

      {hasHostKey ? (
        <section className="flex flex-col gap-3">
          <h2 className="font-serif text-2xl text-white">Inbox</h2>
          <p className="text-sm text-zinc-400">
            Hide a shot here and it will never appear in the gallery, even after
            the film develops.
          </p>
          {photos.length === 0 ? (
            <p className="text-zinc-500">No shots yet. This list refreshes on its own.</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {photos.map((photo) => (
                <figure key={photo.shot_id} className="relative">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={photo.url}
                    alt={`Shot by ${photo.guest_name}`}
                    className={`aspect-[3/4] w-full rounded-lg object-cover ${photo.hidden ? "opacity-30" : ""}`}
                  />
                  <figcaption className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/60 px-2 py-1 text-xs text-white">
                    <span>{photo.guest_name}</span>
                    <button
                      type="button"
                      onClick={() => void toggleHidden(photo)}
                      className="rounded-full bg-white/20 px-2 py-0.5"
                    >
                      {photo.hidden ? "Unhide" : "Hide"}
                    </button>
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
