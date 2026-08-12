import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required by the desktop build: produces .next/standalone/server.js with
  // only the traced dependencies, so the Electron bundle does not have to carry
  // the whole of node_modules. Harmless for the web deployment.
  output: "standalone",
};

export default nextConfig;
