"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { startFilmPreview } from "@/lib/film-preview-gl";
import { useUploadQueue } from "@/lib/use-upload-queue";
import { useI18n } from "@/components/guest/I18nProvider";
import type { MessageKey } from "@/lib/i18n";
import type { FilmPublic } from "@/lib/types";

type Props = {
  code: string;
  token: string;
  film: FilmPublic;
  remaining: number | null;
  onRemainingChange: (remaining: number) => void;
  clipsRemaining: number | null;
  onClipsRemainingChange: (remaining: number) => void;
  onUnauthorized: () => void;
};

// Safari records MP4, everything else WebM. The worker transcodes either.
const CLIP_TYPES = ["video/mp4", "video/webm;codecs=vp9,opus", "video/webm"];

function pickClipType(): string | undefined {
  return CLIP_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

function formatSeconds(total: number): string {
  const whole = Math.floor(total);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function Camera({
  code,
  token,
  film,
  remaining,
  onRemainingChange,
  clipsRemaining,
  onClipsRemainingChange,
  onUnauthorized,
}: Props) {
  const { t } = useI18n();
  const videoRef = useRef<HTMLVideoElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const previewHandleRef = useRef<{ stop: () => void } | null>(null);
  // Stored as a key, not a string, so a language switch retranslates it.
  const [errorKey, setErrorKey] = useState<MessageKey | "">("");
  const [busy, setBusy] = useState(false);
  const [previewReady, setPreviewReady] = useState(false);
  const [usePlainVideo, setUsePlainVideo] = useState(false);
  const [streamReady, setStreamReady] = useState(false);
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [torchOn, setTorchOn] = useState(false);
  const [torchAvailable, setTorchAvailable] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [zoomRange, setZoomRange] = useState<{ min: number; max: number } | null>(null);
  const [closed, setClosed] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [mode, setMode] = useState<"photo" | "clip">("photo");
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const micRef = useRef<MediaStream | null>(null);

  const { snapshot, enqueue, waiting, photosWaiting, clipsWaiting } = useUploadQueue(code, {
    token,
    onRemainingChange,
    onClipsRemainingChange,
    onUnauthorized,
    onClosed: () => {
      setClosed(true);
      setErrorKey("filmClosedCapture");
    },
  });

  const unlimited = film.unlimited_shots;
  const left = unlimited ? 9999 : Math.max((remaining ?? film.shot_limit) - photosWaiting, 0);
  const clipsLeft = Math.max((clipsRemaining ?? film.clips_per_guest) - clipsWaiting, 0);
  const clipMode = film.video_pack && mode === "clip";

  // Per-facing state is reset by the flip handler, not here, so that opening a
  // stream never cascades a second render.
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
        streamRef.current = opened;
        if (videoRef.current) videoRef.current.srcObject = opened;

        const track = opened.getVideoTracks()[0];
        const caps = track.getCapabilities?.() as MediaTrackCapabilities & {
          torch?: boolean;
          zoom?: { min?: number; max?: number };
        };
        setTorchAvailable(Boolean(caps?.torch) && facing === "environment");
        if (caps?.zoom?.max && caps.zoom.max > (caps.zoom.min ?? 1)) {
          setZoomRange({ min: caps.zoom.min ?? 1, max: caps.zoom.max });
        }
        setStreamReady(true);
      })
      .catch(() => setErrorKey("cameraPermission"));

    return () => {
      cancelled = true;
      streamRef.current = null;
      setTorchAvailable(false);
      setZoomRange(null);
      setPreviewReady(false);
      setStreamReady(false);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [facing]);

  useEffect(() => {
    if (!streamReady) return;

    previewHandleRef.current?.stop();
    previewHandleRef.current = null;

    const video = videoRef.current;
    const canvas = previewRef.current;
    if (!video || !canvas) return;

    function attachPreview() {
      if (video!.readyState < video!.HAVE_CURRENT_DATA) return;
      previewHandleRef.current?.stop();
      const handle = startFilmPreview(canvas!, video!, facing === "user");
      if (handle) {
        previewHandleRef.current = handle;
        setPreviewReady(true);
      } else {
        setUsePlainVideo(true);
      }
    }

    video.addEventListener("loadeddata", attachPreview);
    if (video.readyState >= video.HAVE_CURRENT_DATA) attachPreview();

    return () => {
      video.removeEventListener("loadeddata", attachPreview);
      previewHandleRef.current?.stop();
      previewHandleRef.current = null;
    };
  }, [facing, streamReady]);

  // The microphone outlives a camera flip, so it is released only on unmount.
  useEffect(
    () => () => {
      recorderRef.current?.stop();
      micRef.current?.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  useEffect(() => {
    if (!recording) return;
    const started = Date.now();
    const id = window.setInterval(() => {
      const seconds = (Date.now() - started) / 1000;
      setElapsed(seconds);
      if (seconds >= film.clip_max_seconds) recorderRef.current?.stop();
    }, 200);
    return () => window.clearInterval(id);
  }, [recording, film.clip_max_seconds]);

  async function startRecording() {
    const stream = streamRef.current;
    if (!stream || recording || busy || clipsLeft <= 0 || closed) return;
    if (typeof MediaRecorder === "undefined") {
      setErrorKey("clipNotSupported");
      return;
    }
    setErrorKey("");

    // Asked for here, not with the camera: a guest who only takes photos is
    // never shown a microphone prompt.
    let mic = micRef.current;
    if (!mic) {
      try {
        mic = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        micRef.current = mic;
      } catch {
        setErrorKey("micPermission");
        return;
      }
    }

    // The raw camera track, not the shader canvas: the stored clip stays clean.
    const tracks = [...stream.getVideoTracks(), ...mic.getAudioTracks()];
    const mimeType = pickClipType();
    const recorder = new MediaRecorder(
      new MediaStream(tracks),
      mimeType ? { mimeType, videoBitsPerSecond: 4_000_000 } : undefined,
    );
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      recorderRef.current = null;
      setRecording(false);
      setElapsed(0);
      const type = recorder.mimeType || mimeType || "video/webm";
      if (chunks.length > 0) void saveClip(new Blob(chunks, { type }));
    };
    recorder.start(1000);
    recorderRef.current = recorder;
    setRecording(true);
  }

  async function saveClip(clip: Blob) {
    setBusy(true);
    try {
      await enqueue(clip);
      setAnnouncement(t("clipSaved"));
    } catch {
      setErrorKey("shotNotSaved");
    } finally {
      setBusy(false);
    }
  }

  function flipCamera() {
    recorderRef.current?.stop();
    setTorchOn(false);
    setTorchAvailable(false);
    setZoom(1);
    setZoomRange(null);
    setStreamReady(false);
    setPreviewReady(false);
    setUsePlainVideo(false);
    setFacing((f) => (f === "environment" ? "user" : "environment"));
  }

  async function toggleTorch() {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track) return;
    const next = !torchOn;
    try {
      await track.applyConstraints({ advanced: [{ torch: next } as MediaTrackConstraintSet] });
      setTorchOn(next);
    } catch {
      setTorchOn(false);
    }
  }

  async function applyZoom(next: number) {
    const track = streamRef.current?.getVideoTracks()[0];
    if (!track || !zoomRange) return;
    const clamped = Math.min(zoomRange.max, Math.max(zoomRange.min, next));
    try {
      await track.applyConstraints({ advanced: [{ zoom: clamped } as MediaTrackConstraintSet] });
      setZoom(clamped);
    } catch {
      // Some browsers expose zoom in capabilities but reject applyConstraints.
    }
  }

  const shoot = useCallback(async () => {
    const video = videoRef.current;
    if (!video || busy || left <= 0 || closed) return;

    setBusy(true);
    setErrorKey("");
    try {
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth || 1200;
      canvas.height = video.videoHeight || 1600;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Could not capture");
      // Preview shader is display-only; stored originals stay clean.
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      const photo = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.86),
      );
      if (!photo) throw new Error("Could not capture");

      // Disk first, network later. The shutter must not wait for venue wifi.
      await enqueue(photo);

      // The shutter has no sound or flash, so this is the only confirmation
      // a screen reader user gets.
      const after = left - 1;
      const text = unlimited
        ? t("shotSaved")
        : after === 1
          ? t("shotLeftOne")
          : t("shotsLeft", { count: Math.max(after, 0) });

      // A live region stays silent if the text is byte-identical to the last
      // one, which is exactly what happens on an unlimited film.
      setAnnouncement((prev) =>
        prev.replace(/\u200b$/, "") === text ? `${text}\u200b` : text,
      );
    } catch {
      setErrorKey("shotNotSaved");
    } finally {
      setBusy(false);
    }
  }, [busy, closed, enqueue, left, t, unlimited]);

  const empty = clipMode ? clipsLeft <= 0 : left <= 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="relative overflow-hidden rounded-2xl bg-zinc-900">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={
            usePlainVideo
              ? "aspect-[3/4] w-full object-cover"
              : "pointer-events-none absolute h-full w-full opacity-0"
          }
          aria-hidden={!usePlainVideo}
        />
        {!usePlainVideo ? (
          <canvas
            ref={previewRef}
            className="aspect-[3/4] w-full object-cover"
            aria-hidden
          />
        ) : null}
        {!previewReady && !usePlainVideo ? (
          <div className="absolute inset-0 flex items-center justify-center bg-zinc-900 text-sm text-zinc-500">
            {t("startingCamera")}
          </div>
        ) : null}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-between p-4 text-sm text-white">
          <span>{film.title}</span>
          <span className="tabular-nums">
            {recording
              ? `${formatSeconds(elapsed)} / ${formatSeconds(film.clip_max_seconds)}`
              : clipMode
                ? clipsLeft === 1
                  ? t("clipLeftOne")
                  : t("clipsLeft", { count: clipsLeft })
                : unlimited
                  ? t("unlimited")
                  : `${left} / ${film.shot_limit}`}
          </span>
        </div>
        <button
          type="button"
          onClick={flipCamera}
          className="on-preview absolute bottom-4 right-4 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full bg-black/70 px-4 text-sm font-medium text-white"
          aria-label={t("switchCamera")}
        >
          {t("flipCamera")}
        </button>
        {torchAvailable ? (
          <button
            type="button"
            onClick={() => void toggleTorch()}
            className="on-preview absolute bottom-4 left-4 inline-flex min-h-11 min-w-11 items-center justify-center rounded-full bg-black/70 px-4 text-sm font-medium text-white"
            aria-pressed={torchOn}
            aria-label={torchOn ? t("turnTorchOff") : t("turnTorchOn")}
          >
            {torchOn ? t("torchOn") : t("torch")}
          </button>
        ) : null}
        {zoomRange ? (
          <div className="absolute inset-x-4 bottom-20 flex items-center gap-3 rounded-full bg-black/70 px-4 py-2">
            <span className="text-sm text-white tabular-nums">{zoom.toFixed(1)}×</span>
            <input
              type="range"
              min={zoomRange.min}
              max={zoomRange.max}
              step={Math.max(0.1, (zoomRange.max - zoomRange.min) / 20)}
              value={zoom}
              onChange={(event) => void applyZoom(Number(event.target.value))}
              className="on-preview h-11 flex-1 accent-white"
              aria-label={t("zoom")}
              aria-valuetext={t("zoomValue", { value: zoom.toFixed(1) })}
            />
          </div>
        ) : null}
      </div>

      {waiting > 0 ? (
        <p className="text-center text-sm text-zinc-400" role="status" aria-live="polite">
          {snapshot.uploading > 0
            ? t("uploading", { count: waiting })
            : navigatorOnLine()
              ? waiting === 1
                ? t("photoWaiting")
                : t("photosWaiting", { count: waiting })
              : waiting === 1
                ? t("offlineSavedOne")
                : t("offlineSaved", { count: waiting })}
        </p>
      ) : null}

      {snapshot.failed > 0 ? (
        <p className="text-center text-sm text-red-400" role="alert">
          {snapshot.failed === 1
            ? t("shotFailed")
            : t("shotsFailed", { count: snapshot.failed })}
        </p>
      ) : null}

      {errorKey ? (
        <p className="text-center text-sm text-red-400" role="alert">
          {t(errorKey)}
        </p>
      ) : null}

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {film.video_pack ? (
        <div
          className="mx-auto flex rounded-full bg-zinc-900 p-1 text-sm"
          role="radiogroup"
          aria-label={t("modeClip")}
        >
          {(["photo", "clip"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={mode === option}
              disabled={recording}
              onClick={() => setMode(option)}
              className={`min-h-11 rounded-full px-5 ${
                mode === option ? "bg-white text-black" : "text-zinc-300"
              }`}
            >
              {t(option === "photo" ? "modePhoto" : "modeClip")}
            </button>
          ))}
        </div>
      ) : null}

      {clipMode ? (
        <button
          type="button"
          onClick={() => (recording ? recorderRef.current?.stop() : void startRecording())}
          disabled={!recording && (busy || empty || closed)}
          aria-pressed={recording}
          className="mx-auto flex h-20 w-20 items-center justify-center rounded-full border-4 border-white disabled:opacity-40"
          aria-label={recording ? t("stopClip") : t("recordClip")}
        >
          <span
            className={
              recording ? "h-7 w-7 rounded-md bg-red-500" : "h-14 w-14 rounded-full bg-red-500"
            }
          />
        </button>
      ) : (
        <button
          type="button"
          onClick={shoot}
          disabled={busy || empty || closed}
          aria-busy={busy}
          className="mx-auto h-20 w-20 rounded-full border-4 border-white bg-white/90 disabled:opacity-40"
          aria-label={t("takePhoto")}
        />
      )}

      {empty ? (
        <p className="text-center text-sm text-zinc-400">
          {clipMode
            ? t("clipsEmpty")
            : t(film.instant_reveal ? "cameraEmptyLive" : "cameraEmpty")}
        </p>
      ) : null}
    </div>
  );
}

function navigatorOnLine(): boolean {
  return typeof navigator === "undefined" ? true : navigator.onLine;
}
