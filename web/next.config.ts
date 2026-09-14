import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle (.next/standalone) so the Docker runtime
  // image is just Node + the traced deps — see web/Dockerfile (SETUP-05).
  output: "standalone",
};

export default nextConfig;
