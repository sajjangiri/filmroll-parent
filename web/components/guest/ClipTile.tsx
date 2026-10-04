"use client";

import { useState } from "react";

type Props = {
  url: string;
  posterUrl: string | null;
  label: string;
  className?: string;
};

/**
 * A guest clip in a grid. The first signed URL is kept for the life of the
 * tile: galleries re-poll and mint fresh URLs, and swapping ``src`` would
 * restart a clip someone is halfway through watching.
 */
export function ClipTile({ url, posterUrl, label, className }: Props) {
  const [src] = useState(url);
  const [poster] = useState(posterUrl ?? undefined);
  return (
    <video
      src={src}
      poster={poster}
      controls
      playsInline
      preload="none"
      aria-label={label}
      className={className}
    />
  );
}
