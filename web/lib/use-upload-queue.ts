"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import {
  drainQueue,
  enqueueShot,
  getQueueSnapshot,
  getServerQueueSnapshot,
  isAuthError,
  isCapError,
  isClosedError,
  onShotFailed,
  onShotUploaded,
  refreshSnapshot,
  subscribeQueue,
  type QueueSnapshot,
} from "@/lib/upload-queue";

type Options = {
  token: string;
  onRemainingChange: (remaining: number) => void;
  onUnauthorized: () => void;
  onClosed: () => void;
};

export function useUploadQueue(code: string, options: Options) {
  const snapshot: QueueSnapshot = useSyncExternalStore(
    subscribeQueue,
    () => getQueueSnapshot(code),
    getServerQueueSnapshot,
  );

  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  useEffect(() => {
    void refreshSnapshot(code);
    void drainQueue(code);

    const resume = () => {
      void drainQueue(code);
    };
    window.addEventListener("online", resume);
    document.addEventListener("visibilitychange", resume);

    const offUploaded = onShotUploaded((shot, remaining) => {
      if (shot.code !== code) return;
      optionsRef.current.onRemainingChange(remaining);
    });

    const offFailed = onShotFailed((shot, error) => {
      if (shot.code !== code) return;
      if (isAuthError(error)) optionsRef.current.onUnauthorized();
      if (isClosedError(error)) optionsRef.current.onClosed();
      if (isCapError(error)) optionsRef.current.onRemainingChange(0);
    });

    return () => {
      window.removeEventListener("online", resume);
      document.removeEventListener("visibilitychange", resume);
      offUploaded();
      offFailed();
    };
  }, [code]);

  const enqueue = useCallback(
    async (photo: Blob) => {
      await enqueueShot({ code, token: optionsRef.current.token, photo });
    },
    [code],
  );

  return { snapshot, enqueue, waiting: snapshot.pending + snapshot.uploading };
}
