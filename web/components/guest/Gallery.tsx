"use client";

import { useEffect, useState } from "react";
import { ClipTile } from "@/components/guest/ClipTile";
import { I18nProvider, useI18n } from "@/components/guest/I18nProvider";
import { LanguagePicker } from "@/components/guest/LanguagePicker";
import { getFilm, getGallery, loadGuestToken, reportShot } from "@/lib/api";
import type { FilmPublic, GalleryResponse } from "@/lib/types";

export function Gallery({ code }: { code: string }) {
  return (
    <I18nProvider>
      <GalleryInner code={code} />
    </I18nProvider>
  );
}

function GalleryInner({ code }: { code: string }) {
  const { locale, t } = useI18n();
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [gallery, setGallery] = useState<GalleryResponse | null>(null);
  const [error, setError] = useState("");
  const [guestToken, setGuestToken] = useState<string | null>(null);
  const [reported, setReported] = useState<Set<string>>(new Set());
  const [announcement, setAnnouncement] = useState("");

  async function report(shotId: string) {
    if (!guestToken) return;
    // Optimistic: the host's count is the thing that matters, and a guest who
    // taps report wants to stop thinking about it immediately.
    setReported((current) => new Set(current).add(shotId));
    setAnnouncement(t("reportThanks"));
    try {
      await reportShot(code, shotId, guestToken, "inappropriate");
    } catch {
      setReported((current) => {
        const next = new Set(current);
        next.delete(shotId);
        return next;
      });
      setAnnouncement(t("reportFailed"));
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const token = loadGuestToken(code);
        const [loadedFilm, loadedGallery] = await Promise.all([
          getFilm(code),
          getGallery(code, token),
        ]);
        if (cancelled) return;
        setFilm(loadedFilm);
        setGallery(loadedGallery);
        setGuestToken(token);
      } catch {
        if (!cancelled) setError("failed");
      }
    }
    void load();
    const id = window.setInterval(() => {
      void load();
    }, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [code]);

  if (error) {
    return (
      <p className="p-8 text-red-400" role="alert">
        {t("couldNotLoadFilm")}
      </p>
    );
  }
  if (!film || !gallery) {
    return (
      <p className="p-8 text-zinc-400" role="status" aria-live="polite" aria-busy="true">
        {t("loading")}
      </p>
    );
  }

  // The server sends no photo URLs at all before a film develops, so there is
  // nothing here to accidentally render early.
  if (!gallery.is_developed) {
    return (
      <main className="mx-auto flex min-h-full max-w-md flex-col justify-center gap-3 p-8">
        <LanguagePicker />
        <h1 className="font-serif text-3xl text-white">{film.title}</h1>
        <p className="text-zinc-300">
          {t("stillDeveloping", {
            when: new Date(film.reveal_at).toLocaleString(locale),
          })}
        </p>
        <p className="text-sm text-zinc-400">
          {t("shotsWaiting", { count: gallery.shot_count })}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-full max-w-3xl flex-col gap-8 p-6">
      <header className="flex flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">
            {film.instant_reveal ? t("live") : t("developed")}
          </p>
          <LanguagePicker />
        </div>
        <h1 className="font-serif text-4xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {film.shared_gallery
            ? t("galleryStats", {
                shots: gallery.shot_count,
                people: film.guest_count,
              })
            : guestToken
              ? t("privateAlbumOwn")
              : t("privateAlbum")}
        </p>
      </header>

      {gallery.photos.length === 0 ? (
        film.shared_gallery ? (
          <p className="text-zinc-400">{t("noOneShot")}</p>
        ) : guestToken ? (
          <p className="text-zinc-400">{t("privateAlbumEmpty")}</p>
        ) : null
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {gallery.photos.map((photo) => (
            <figure key={photo.shot_id} className="relative">
              {photo.kind === "clip" ? (
                <ClipTile
                  url={photo.url}
                  posterUrl={photo.poster_url}
                  label={t("clipBy", { name: photo.guest_name })}
                  className="aspect-[3/4] w-full rounded-lg bg-black object-cover"
                />
              ) : (
                <>
                  {/* Signed, short-lived storage URLs; the image optimizer
                      would cache them past their expiry. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={photo.url}
                    alt={t("shotBy", { name: photo.guest_name })}
                    loading="lazy"
                    className="aspect-[3/4] w-full rounded-lg object-cover"
                  />
                </>
              )}
              {/* A clip's own controls sit along the bottom edge. */}
              <figcaption
                className={`absolute inset-x-0 flex items-center justify-between gap-2 bg-black/75 px-2 py-1.5 text-sm text-white ${
                  photo.kind === "clip" ? "top-0 rounded-t-lg" : "bottom-0 rounded-b-lg"
                }`}
              >
                <span className="truncate">{photo.guest_name}</span>
                {/* Only people who joined can report, so the control appears
                    only for a device holding a guest token. */}
                {guestToken ? (
                  reported.has(photo.shot_id) ? (
                    <span className="shrink-0 text-xs text-zinc-300">
                      {t("reported")}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void report(photo.shot_id)}
                      className="shrink-0 rounded-full bg-white/20 px-2 py-1 text-xs"
                      aria-label={t("reportPhotoBy", { name: photo.guest_name })}
                    >
                      {t("report")}
                    </button>
                  )
                ) : null}
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </main>
  );
}
