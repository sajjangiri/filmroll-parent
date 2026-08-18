"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, captureShot } from "@/lib/api";
import type { FilmPublic } from "@/lib/types";

type Props = {
  code: string;
  token: string;
  film: FilmPublic;
  remaining: number | null;
  onRemainingChange: (remaining: number) => void;
  onUnauthorized: () => void;
};

export function Camera({
  code,
  token,
  film,
  remaining,
  onRemainingChange,
  onUnauthorized,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [facing, setFacing] = useState<"environment" | "user">("environment");

  useEffect(() => {
    let stream: MediaStream | undefined;
    let cancelled = false;

    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1600 } },
        audio: false,
      })
      .then((opened) => {
        if (cancelled) {
          opened.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = opened;
        if (videoRef.current) videoRef.current.srcObject = opened;
      })
      .catch(() => setError("Camera permission is required to shoot."));

    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [facing]);

  const shoot = useCallback(async () => {
    const video = videoRef.current;
    if (!video || busy || remaining === 0) return;

    setBusy(true);
    setError("");
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1200;
      canvas.height = video.videoHeight || 1600;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Could not capture");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const photo = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.86),
      );
      if (!photo) throw new Error("Could not capture");

      // Reserves a slot, uploads straight to storage, then confirms. Retries
      // inside reuse the same shot id, so a flaky connection cannot burn shots.
      const committed = await captureShot(code, token, photo);
      onRemainingChange(committed.shots_remaining);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        onUnauthorized();
      } else if (err instanceof ApiError && err.status === 409) {
        setError("Your roll is finished.");
        onRemainingChange(0);
      } else if (err instanceof ApiError && err.status === 410) {
        setError("This film has closed.");
      } else {
        setError("That shot did not save. Try again.");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, code, onRemainingChange, onUnauthorized, remaining, token]);

  const empty = remaining === 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="relative overflow-hidden rounded-2xl bg-zinc-900">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="aspect-[3/4] w-full object-cover"
        />
        <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-4 text-sm text-white">
          <span>{film.title}</span>
          <span>
            {remaining ?? film.shot_limit} / {film.shot_limit}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))}
          className="absolute bottom-4 right-4 rounded-full bg-black/60 px-3 py-2 text-xs text-white"
        >
          Flip
        </button>
      </div>

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <button
        type="button"
        onClick={shoot}
        disabled={busy || empty}
        className="mx-auto h-20 w-20 rounded-full border-4 border-white bg-white/90 disabled:opacity-40"
        aria-label="Take photo"
      />

      {empty ? (
        <p className="text-center text-sm text-zinc-400">
          This camera is empty. Photos unlock when the film develops.
        </p>
      ) : null}
    </div>
  );
}
