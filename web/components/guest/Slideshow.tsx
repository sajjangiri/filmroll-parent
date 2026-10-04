"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { I18nProvider, useI18n } from "@/components/guest/I18nProvider";
import { API_URL, getFilm, getGallery } from "@/lib/api";
import type { FilmPublic, GalleryPhoto, GalleryResponse } from "@/lib/types";

const PHOTO_MS = 7000;
const POLL_MS = 8000;

export function Slideshow({ code }: { code: string }) {
  return (
    <I18nProvider>
      <SlideshowInner code={code} />
    </I18nProvider>
  );
}

/**
 * What to show after ``fromId``. Shots nobody has seen yet go first, newest
 * first, so a photo taken on the dance floor is on the wall within one poll;
 * once everything has had a turn the roll simply cycles in upload order.
 */
function pickNext(
  photos: GalleryPhoto[],
  shown: Set<string>,
  fromId: string | null,
): GalleryPhoto | null {
  if (photos.length === 0) return null;
  const unseen = photos.filter((photo) => !shown.has(photo.shot_id));
  if (unseen.length > 0) return unseen[unseen.length - 1];
  const index = photos.findIndex((photo) => photo.shot_id === fromId);
  return photos[(index + 1) % photos.length];
}

type SlideState = { id: string | null; shown: Set<string>; seq: number };

function SlideshowInner({ code }: { code: string }) {
  const { locale, t } = useI18n();
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [gallery, setGallery] = useState<GalleryResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [slide, setSlide] = useState<SlideState>({ id: null, shown: new Set(), seq: 0 });
  const [paused, setPaused] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  // The public gallery, with no token: the wall shows exactly what any guest
  // holding the link could see, so hidden shots and the reveal gate carry over.
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [loadedFilm, loadedGallery] = await Promise.all([getFilm(code), getGallery(code)]);
        if (cancelled) return;
        setFilm(loadedFilm);
        setGallery(loadedGallery);
        setFailed(false);
      } catch {
        // Venue wifi drops; keep showing what is already loaded.
        if (!cancelled) setFailed(true);
      }
    }
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [code]);

  const photos = useMemo(() => gallery?.photos ?? [], [gallery]);
  // A shot the host has just hidden drops out of the next poll, and the
  // lookup failing is what moves the wall straight on from it.
  const current =
    photos.find((photo) => photo.shot_id === slide.id) ??
    pickNext(photos, slide.shown, slide.id);
  // Commit the first pick during render (React re-renders before painting).
  // Without that, a poll that lands a newer shot would replace the one already
  // on the wall before ``next`` ever ran.
  if (slide.id === null && current) {
    setSlide({ ...slide, id: current.shot_id });
  }

  const photosRef = useRef(photos);
  const currentIdRef = useRef<string | null>(null);
  useEffect(() => {
    photosRef.current = photos;
    currentIdRef.current = current?.shot_id ?? null;
  });

  const next = useCallback((fromId: string) => {
    setSlide((prev) => {
      const shown = new Set(prev.shown).add(fromId);
      const upcoming = pickNext(photosRef.current, shown, fromId);
      return { id: upcoming?.shot_id ?? null, shown, seq: prev.seq + 1 };
    });
  }, []);

  const currentId = current?.shot_id ?? null;
  const currentKind = current?.kind ?? null;
  const clipLimitMs = ((film?.clip_max_seconds ?? 15) + 5) * 1000;

  // Photos advance on a timer. Clips advance when they end; the timer is only
  // a backstop for one that stalls.
  useEffect(() => {
    if (!currentId || paused) return;
    const id = window.setTimeout(
      () => next(currentId),
      currentKind === "clip" ? clipLimitMs : PHOTO_MS,
    );
    return () => window.clearTimeout(id);
  }, [currentId, currentKind, clipLimitMs, paused, next, slide.seq]);

  // Warm the browser cache so the next slide appears without a blank frame.
  useEffect(() => {
    if (!currentId) return;
    const upcoming = pickNext(photos, new Set(slide.shown).add(currentId), currentId);
    if (upcoming && upcoming.kind === "photo") {
      const image = new Image();
      image.src = upcoming.display_url ?? upcoming.url;
    }
  }, [currentId, photos, slide.shown]);

  // A projector laptop left alone will otherwise dim and lock mid-party.
  useEffect(() => {
    let lock: WakeLockSentinel | null = null;
    async function acquire() {
      try {
        lock = (await navigator.wakeLock?.request("screen")) ?? null;
      } catch {
        // Unsupported or refused; the slideshow still runs.
      }
    }
    const onVisible = () => {
      if (document.visibilityState === "visible") void acquire();
    };
    void acquire();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      void lock?.release();
    };
  }, []);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    const onKey = (event: KeyboardEvent) => {
      if (event.key === " ") {
        event.preventDefault();
        setPaused((value) => !value);
      } else if (event.key === "ArrowRight" && currentIdRef.current) {
        next(currentIdRef.current);
      }
    };
    document.addEventListener("fullscreenchange", onChange);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      window.removeEventListener("keydown", onKey);
    };
  }, [next]);

  const qrSrc = `${API_URL}/v1/films/${code}/qr.svg`;

  if (!film || !gallery) {
    return (
      <main className="fixed inset-0 flex items-center justify-center bg-black text-zinc-500">
        <p role="status">{failed ? t("couldNotLoadFilm") : t("loading")}</p>
      </main>
    );
  }

  const fullscreenButton = fullscreen ? null : (
    <button
      type="button"
      onClick={() => void document.documentElement.requestFullscreen?.()}
      className="absolute right-6 top-6 z-10 inline-flex min-h-11 items-center rounded-full bg-white/15 px-5 text-sm text-white hover:bg-white/25"
    >
      {t("slideshowFullscreen")}
    </button>
  );

  if (!current) {
    const message = !film.shared_gallery
      ? t("slideshowPrivate")
      : !gallery.is_developed
        ? t("slideshowWaiting", {
            count: gallery.shot_count,
            when: new Date(film.reveal_at).toLocaleString(locale),
          })
        : t("slideshowEmpty");
    return (
      <main className="fixed inset-0 flex flex-col items-center justify-center gap-[3vh] bg-black p-8 text-center">
        {fullscreenButton}
        {/* Sized to the screen height: the same page runs on a 768 px laptop
            and a 1080 p projector. */}
        <h1 className="font-serif text-[clamp(2.5rem,8vh,5rem)] leading-tight text-white">
          {film.title}
        </h1>
        <div className="rounded-3xl bg-white p-[2vh]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qrSrc} alt="" className="h-[min(20rem,42vh)] w-[min(20rem,42vh)]" />
        </div>
        <p className="text-[clamp(1.25rem,3.5vh,2rem)] text-zinc-200">{t("slideshowScan")}</p>
        <p className="max-w-3xl text-[clamp(1rem,2.8vh,1.5rem)] text-zinc-400">{message}</p>
      </main>
    );
  }

  return (
    <main className={`fixed inset-0 overflow-hidden bg-black ${fullscreen ? "cursor-none" : ""}`}>
      {fullscreenButton}
      <div key={`${current.shot_id}-${slide.seq}`} className="slide-in absolute inset-0">
        {current.kind === "clip" ? (
          <ClipSlide
            url={current.url}
            posterUrl={current.poster_url}
            paused={paused}
            onDone={() => next(current.shot_id)}
          />
        ) : (
          <PhotoSlide
            url={current.display_url ?? current.url}
            onError={() => next(current.shot_id)}
          />
        )}
      </div>

      <p className="slide-caption absolute bottom-8 left-8 text-3xl font-medium text-white">
        {current.guest_name}
      </p>

      <div className="absolute bottom-8 right-8 flex items-center gap-4 rounded-2xl bg-black/70 p-3 pr-5">
        <div className="rounded-xl bg-white p-2">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={qrSrc} alt="" className="h-24 w-24" />
        </div>
        <div className="flex flex-col text-left">
          <span className="text-lg text-white">{t("slideshowScan")}</span>
          <span className="font-serif text-2xl text-zinc-200">{film.title}</span>
        </div>
      </div>

      {paused ? (
        <p className="absolute left-8 top-8 rounded-full bg-black/70 px-4 py-2 text-sm text-white">
          {t("slideshowPaused")}
        </p>
      ) : null}
    </main>
  );
}

/** The signed URL is pinned per slide; a re-poll would otherwise reload the image. */
function PhotoSlide({ url, onError }: { url: string; onError: () => void }) {
  const [src] = useState(url);
  return (
    // Signed, short-lived storage URLs; the image optimizer would cache them
    // past their expiry.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" onError={onError} className="h-full w-full object-contain" />
  );
}

/** Muted, because autoplay with sound is blocked and a venue has its own music. */
function ClipSlide({
  url,
  posterUrl,
  paused,
  onDone,
}: {
  url: string;
  posterUrl: string | null;
  paused: boolean;
  onDone: () => void;
}) {
  const [src] = useState(url);
  const [poster] = useState(posterUrl ?? undefined);
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (paused) video.pause();
    else void video.play().catch(() => undefined);
  }, [paused]);
  return (
    <video
      ref={videoRef}
      src={src}
      poster={poster}
      autoPlay
      muted
      playsInline
      onEnded={onDone}
      onError={onDone}
      className="h-full w-full object-contain"
    />
  );
}
