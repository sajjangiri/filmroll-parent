"use client";

import { useEffect, useState } from "react";
import { getFilm, getGallery } from "@/lib/api";
import type { FilmPublic, GalleryResponse } from "@/lib/types";

export function Gallery({ code }: { code: string }) {
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [gallery, setGallery] = useState<GalleryResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [loadedFilm, loadedGallery] = await Promise.all([
          getFilm(code),
          getGallery(code),
        ]);
        if (cancelled) return;
        setFilm(loadedFilm);
        setGallery(loadedGallery);
      } catch {
        if (!cancelled) setError("Could not load this film.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) return <p className="p-8 text-red-400">{error}</p>;
  if (!film || !gallery) return <p className="p-8 text-zinc-400">Loading…</p>;

  // The server sends no photo URLs at all before a film develops, so there is
  // nothing here to accidentally render early.
  if (!gallery.is_developed) {
    return (
      <main className="mx-auto flex min-h-full max-w-md flex-col justify-center gap-3 p-8">
        <h1 className="font-serif text-3xl text-white">{film.title}</h1>
        <p className="text-zinc-400">
          This film is still developing. Come back{" "}
          {new Date(film.reveal_at).toLocaleString()}.
        </p>
        <p className="text-sm text-zinc-500">
          {gallery.shot_count} shots waiting.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-full max-w-3xl flex-col gap-8 p-6">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Developed</p>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {gallery.shot_count} shots from {film.guest_count} people
        </p>
      </header>

      {gallery.photos.length === 0 ? (
        <p className="text-zinc-400">No one shot this roll.</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {gallery.photos.map((photo) => (
            <figure key={photo.shot_id} className="relative">
              {/* Signed, short-lived storage URLs; the image optimizer would
                  cache them past their expiry. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={photo.url}
                alt={`Shot by ${photo.guest_name}`}
                loading="lazy"
                className="aspect-[3/4] w-full rounded-lg object-cover"
              />
              <figcaption className="absolute inset-x-0 bottom-0 bg-black/50 px-2 py-1 text-xs text-white">
                {photo.guest_name}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </main>
  );
}
