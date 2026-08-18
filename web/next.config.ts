import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A stray lockfile in a parent directory makes Turbopack infer the wrong
  // workspace root, which changes how files resolve. Pinning it to this
  // directory keeps dev and build reading the same tree.
  turbopack: {
    root: path.join(import.meta.dirname, ".."),
  },
};

export default nextConfig;
