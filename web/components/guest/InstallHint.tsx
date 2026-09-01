"use client";

import { useSyncExternalStore } from "react";

const neverChanges = () => () => {};

function readShouldShow(): boolean {
  const standalone = window.matchMedia("(display-mode: standalone)").matches;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent);
  return ios && !standalone;
}

export function InstallHint() {
  const show = useSyncExternalStore(neverChanges, readShouldShow, () => false);
  if (!show) return null;

  return (
    <p className="text-xs text-zinc-500">
      Add to Home Screen from the share menu to keep shooting if the browser tab
      is closed.
    </p>
  );
}
