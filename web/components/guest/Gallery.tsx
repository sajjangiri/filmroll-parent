"use client";

import { useEffect, useState } from "react";
import { ClipTile } from "@/components/guest/ClipTile";
import { I18nProvider, useI18n } from "@/components/guest/I18nProvider";
import { LanguagePicker } from "@/components/guest/LanguagePicker";
import { getFilm, getGallery, loadGuestToken, reportShot } from "@/lib/api";
import type { FilmPublic, GalleryPhoto, GalleryResponse } from "@/lib/types";

/**
 * Hand one photo or clip to the device. Phones get the share sheet, whose
 * "Save Image" is the only way into the iOS photo library from a web page;
 * desktops get a download. Browsers ignore `download` on a cross-origin link,
 * so the bytes are fetched first, which needs the bucket to allow GET from this
 * origin.
 */
async function saveMedia(url: string, basename: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    // Bucket CORS is missing. Opening the file still lets the guest long-press it.
    window.open(url, "_blank", "noopener");
    return;
  }
  if (!response.ok) throw new Error(`save failed: ${response.status}`);
  const blob = await response.blob();
  const extension = blob.type.startsWith("video/") ? "mp4" : "jpg";
  const file = new File([blob], `${basename}.${extension}`, { type: blob.type });

  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file] });
      return;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      // Safari drops the tap's activation if the fetch was slow, so share is
      // refused; a download still works.
      if (!(error instanceof DOMException && error.name === "NotAllowedError")) throw error;
    }
  }

  const href = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = href;
  link.download = file.name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

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
  const [saving, setSaving] = useState<Set<string>>(new Set());
  const [saveFailed, setSaveFailed] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  async function save(photo: GalleryPhoto) {
    setSaving((current) => new Set(current).add(photo.shot_id));
    setSaveFailed(false);
    try {
      await saveMedia(photo.url, `filmroll-${code}-${photo.shot_id.slice(0, 8)}`);
    } catch {
      setSaveFailed(true);
    } finally {
      setSaving((current) => {
        const next = new Set(current);
        next.delete(photo.shot_id);
        return next;
      });
    }
  }

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

      {saveFailed ? (
        <p className="text-sm text-red-400" role="alert">
          {t("saveFailed")}
        </p>
      ) : null}

      {gallery.photos.length === 0 ? (
        film.shared_gallery ? (
          <p className="text-zinc-400">{t("noOneShot")}</p>
        ) : guestToken ? (
          <p className="text-zinc-400">{t("privateAlbumEmpty")}</p>
        ) : null
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {gallery.photos.map((photo) => (
            <div key={photo.shot_id} className="flex flex-col gap-1.5">
              <figure className="relative">
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
                  className={`absolute inset-x-0 truncate bg-black/75 px-2 py-1.5 text-sm text-white ${
                    photo.kind === "clip" ? "top-0 rounded-t-lg" : "bottom-0 rounded-b-lg"
                  }`}
                >
                  {photo.guest_name}
                </figcaption>
              </figure>
              {/* Below the tile rather than over it: two 44px controls and a
                  name do not fit across a phone's half-width column. */}
              <div className="flex flex-wrap gap-2">
                {/* Anyone who can see the tile could already long-press it. */}
                <button
                  type="button"
                  onClick={() => void save(photo)}
                  disabled={saving.has(photo.shot_id)}
                  className="inline-flex min-h-11 items-center justify-center rounded-full bg-white/10 px-4 text-sm text-white disabled:opacity-50"
                  aria-label={t(photo.kind === "clip" ? "saveClipBy" : "savePhotoBy", {
                    name: photo.guest_name,
                  })}
                >
                  {t("save")}
                </button>
                {/* Only people who joined can report, so the control appears
                    only for a device holding a guest token. */}
                {guestToken ? (
                  reported.has(photo.shot_id) ? (
                    <span className="inline-flex min-h-11 items-center px-2 text-sm text-zinc-400">
                      {t("reported")}
                    </span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void report(photo.shot_id)}
                      className="inline-flex min-h-11 items-center justify-center rounded-full bg-white/10 px-4 text-sm text-zinc-300"
                      aria-label={t("reportPhotoBy", { name: photo.guest_name })}
                    >
                      {t("report")}
                    </button>
                  )
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}

      <p aria-live="polite" className="sr-only">
        {announcement}
      </p>
    </main>
  );
}
