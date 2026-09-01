import { useCallback, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import {
  drainQueue,
  enqueueShot,
  getQueueSnapshot,
  isAuthError,
  isCapError,
  isClosedError,
  onShotFailed,
  onShotUploaded,
  refreshSnapshot,
  subscribeQueue,
  type QueueSnapshot,
} from "./upload-queue";

type Options = {
  token: string;
  onRemainingChange: (remaining: number) => void;
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
      unsubscribe();
      app.remove();
      offUploaded();
      offFailed();
    };
  }, [code]);

  const enqueue = useCallback(
    async (fileUri: string) => {
      await enqueueShot({ code, token: optionsRef.current.token, fileUri });
    },
    [code],
  );

  return { snapshot, enqueue, waiting: snapshot.pending + snapshot.uploading };
}
