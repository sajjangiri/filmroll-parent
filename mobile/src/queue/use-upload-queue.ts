import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import {
  drainQueue,
  enqueueShot,
  getQueueSnapshot,
  isAuthError,
  isCapError,
  isClipCapError,
  isClosedError,
  onShotFailed,
  onShotUploaded,
  refreshSnapshot,
  subscribeQueue,
  type QueueSnapshot,
} from "./upload-queue";
import type { ShotKind } from "../api/types";

type Options = {
  token: string;
  onRemainingChange: (remaining: number) => void;
  onClipsRemainingChange: (remaining: number) => void;
  onUnauthorized: () => void;
  onClosed: () => void;
};

export function useUploadQueue(code: string, options: Options) {
  const [snapshot, setSnapshot] = useState<QueueSnapshot>(() => getQueueSnapshot(code));

  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  useEffect(() => {
    const unsubscribe = subscribeQueue(() => setSnapshot(getQueueSnapshot(code)));
    void refreshSnapshot(code);
    void drainQueue(code);

    const resume = () => {
      void drainQueue(code);
    };
    const app = AppState.addEventListener("change", (state) => {
      if (state === "active") resume();
    });

    const offUploaded = onShotUploaded((shot, committed) => {
      if (shot.code !== code) return;
      optionsRef.current.onRemainingChange(committed.shots_remaining);
      optionsRef.current.onClipsRemainingChange(committed.clips_remaining);
    });

    const offFailed = onShotFailed((shot, error) => {
      if (shot.code !== code) return;
      if (isAuthError(error)) optionsRef.current.onUnauthorized();
      if (isClosedError(error)) optionsRef.current.onClosed();
      if (isCapError(error)) optionsRef.current.onRemainingChange(0);
      if (isClipCapError(error)) optionsRef.current.onClipsRemainingChange(0);
    });

    return () => {
      unsubscribe();
      app.remove();
      offUploaded();
      offFailed();
    };
  }, [code]);

  const enqueue = useCallback(
    async (fileUri: string, kind: ShotKind = "photo") => {
      await enqueueShot({ code, token: optionsRef.current.token, fileUri, kind });
    },
    [code],
  );

  const waiting = snapshot.pending + snapshot.uploading;
  return {
    snapshot,
    enqueue,
    waiting,
    photosWaiting: waiting - snapshot.clipsWaiting,
    clipsWaiting: snapshot.clipsWaiting,
  };
}
