"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useUploadQueue } from "@/lib/use-upload-queue";
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
  const [closed, setClosed] = useState(false);

  const { snapshot, enqueue, waiting } = useUploadQueue(code, {
    token,
    onRemainingChange,
    onUnauthorized,
    onClosed: () => {
      setClosed(true);
      setError("This film has closed.");
    },
  });

  const left = Math.max((remaining ?? film.shot_limit) - waiting, 0);

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
    if (!video || busy || left <= 0 || closed) return;

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

      // Disk first, network later. The shutter must not wait for venue wifi.
      await enqueue(photo);
    } catch {
      setError("That shot did not save on this device. Try again.");
    } finally {
      setBusy(false);
    }
  }, [busy, closed, enqueue, left]);

  const empty = left <= 0;

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
            {left} / {film.shot_limit}
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

      {waiting > 0 ? (
        <p className="text-center text-sm text-zinc-400" role="status">
          {snapshot.uploading > 0
            ? `Uploading… ${waiting} waiting`
            : navigatorOnLine()
              ? `${waiting} ${waiting === 1 ? "photo" : "photos"} waiting to upload`
              : `Offline · ${waiting} ${waiting === 1 ? "photo" : "photos"} saved on this phone`}
        </p>
      ) : null}

      {snapshot.failed > 0 ? (
        <p className="text-center text-sm text-red-400">
          {snapshot.failed} {snapshot.failed === 1 ? "shot" : "shots"} could not be uploaded.
        </p>
      ) : null}

      {error ? <p className="text-sm text-red-400">{error}</p> : null}

      <button
        type="button"
        onClick={shoot}
        disabled={busy || empty || closed}
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

function navigatorOnLine(): boolean {
  return typeof navigator === "undefined" ? true : navigator.onLine;
}
