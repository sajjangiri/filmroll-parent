"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Guest, PublicFilm } from "@/lib/types";

type Props = {
  code: string;
  film: PublicFilm;
  guest: Guest;
  onUpdate: (film: PublicFilm, guest: Guest) => void;
};

export function Camera({ code, film, guest, onUpdate }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const remaining = film.shotLimit - guest.shotsTaken;

  useEffect(() => {
    let stream: MediaStream | undefined;
    navigator.mediaDevices
      .getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
        audio: false,
      })
      .then((s) => {
        stream = s;
        if (videoRef.current) {
          videoRef.current.srcObject = s;
        }
      })
      .catch(() => setError("Camera permission is required to shoot."));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  const shoot = useCallback(async () => {
    const video = videoRef.current;
    if (!video || remaining <= 0 || busy) return;
    setBusy(true);
    setError("");
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1080;
      canvas.height = video.videoHeight || 1440;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Could not capture");
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/jpeg", 0.86),
      );
      if (!blob) throw new Error("Could not capture");
      const form = new FormData();
      form.set("guestId", guest.id);
      form.set("photo", blob, "shot.jpg");
      const res = await fetch(`/api/films/${code}/shots`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      onUpdate(data.film, data.guest);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }, [busy, code, guest.id, onUpdate, remaining]);

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
            {remaining} / {film.shotLimit}
          </span>
        </div>
      </div>
      {error ? <p className="text-sm text-red-400">{error}</p> : null}
      <button
        type="button"
        onClick={shoot}
        disabled={busy || remaining <= 0}
        className="mx-auto h-20 w-20 rounded-full border-4 border-white bg-white/90 disabled:opacity-40"
        aria-label="Take photo"
      />
      {remaining <= 0 ? (
        <p className="text-center text-sm text-zinc-400">
          This camera is empty. Photos unlock when the film develops.
        </p>
      ) : null}
    </div>
  );
}
