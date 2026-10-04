"use client";

import { useCallback, useEffect, useState } from "react";
import { Camera } from "@/components/guest/Camera";
import { I18nProvider, useI18n } from "@/components/guest/I18nProvider";
import { InstallHint } from "@/components/guest/InstallHint";
import { LanguagePicker } from "@/components/guest/LanguagePicker";
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
  return (
    <I18nProvider>
      <GuestAppInner code={code} />
    </I18nProvider>
  );
}

function GuestAppInner({ code }: { code: string }) {
  const { t } = useI18n();
  const [film, setFilm] = useState<FilmPublic | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [clipsRemaining, setClipsRemaining] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
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
        setToken(loadGuestToken(code));
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError && err.status === 404
              ? t("filmCodeMissing")
              : t("couldNotReachFilm"),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, t]);

  async function onJoin(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setJoining(true);
    try {
      const joined = await joinFilm(code, name.trim(), pin.trim() || undefined);
      saveGuestToken(code, joined.guest_token);
      setToken(joined.guest_token);
      setRemaining(joined.shots_remaining);
      setClipsRemaining(joined.clips_remaining);
      setFilm(await getFilm(code));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? t("filmFull")
          : err instanceof ApiError && err.status === 410
            ? t("filmClosed")
            : err instanceof ApiError && err.status === 429
              ? t("tooManyAttempts")
              : err instanceof ApiError && err.status === 403
                ? t("wrongPin")
                : t("couldNotJoin"),
      );
    } finally {
      setJoining(false);
    }
  }

  const onUnauthorized = useCallback(() => {
    clearGuestToken(code);
    setToken(null);
    setError(t("cameraExpired"));
  }, [code, t]);

  if (loading) {
    return (
      <p className="text-zinc-400" aria-live="polite" aria-busy="true">
        {t("loadingFilm")}
      </p>
    );
  }
  if (!film) {
    return (
      <p className="text-red-400" role="alert">
        {error || t("filmNotFound")}
      </p>
    );
  }

  const shotsLabel = film.unlimited_shots
    ? t("unlimitedShots")
    : t("shotsEach", { count: film.shot_limit });

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6">
      <header className="flex flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          <p className="text-xs uppercase tracking-[0.2em] text-zinc-400">{t("brand")}</p>
          <LanguagePicker />
        </div>
        <h1 className="font-serif text-3xl text-white">{film.title}</h1>
        <p className="text-sm text-zinc-400">
          {t("guestLine", {
            guestCount: film.guest_count,
            guestCap: film.guest_cap,
            shotsLabel,
          })}
        </p>
        <InstallHint />
      </header>

      {film.is_developed ? (
        <a
          href={`/f/${code}/gallery`}
          className="rounded-full bg-white px-5 py-3 text-center text-sm font-medium text-black"
        >
          {film.instant_reveal ? t("viewLiveGallery") : t("viewGallery")}
        </a>
      ) : null}

      {!token ? (
        <form onSubmit={onJoin} className="flex flex-col gap-3">
          <label htmlFor="guest-name" className="text-sm text-zinc-400">
            {t("joinLabel")}
          </label>
          <input
            id="guest-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("namePlaceholder")}
            required
            autoFocus
            autoComplete="name"
            enterKeyHint="go"
            maxLength={80}
            className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-3 text-base text-zinc-100 outline-none focus:border-zinc-500"
          />
          {film.requires_pin ? (
            <>
              <label htmlFor="guest-pin" className="text-sm text-zinc-400">
                {t("pinLabel")}
              </label>
              <input
                id="guest-pin"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                placeholder={t("pinPlaceholder")}
                required
                // Digits only, so phones offer a keypad rather than a keyboard.
                inputMode="numeric"
                autoComplete="off"
                enterKeyHint="go"
                maxLength={20}
                className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-3 text-base tracking-[0.3em] text-zinc-100 outline-none focus:border-zinc-500"
              />
            </>
          ) : null}
          {error ? (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={
              film.is_closed || joining || !name.trim() || (film.requires_pin && !pin.trim())
            }
            className="rounded-full bg-white px-5 py-3.5 text-base font-medium text-black disabled:opacity-40"
          >
            {film.is_closed ? t("joinClosed") : joining ? t("joining") : t("joinFilm")}
          </button>
        </form>
      ) : film.is_closed ? (
        <p className="text-zinc-400">
          {film.instant_reveal ? t("shootingEndedLive") : t("shootingEnded")}
        </p>
      ) : (
        <Camera
          code={code}
          token={token}
          film={film}
          remaining={remaining}
          onRemainingChange={setRemaining}
          clipsRemaining={clipsRemaining}
          onClipsRemainingChange={setClipsRemaining}
          onUnauthorized={onUnauthorized}
        />
      )}
    </div>
  );
}
