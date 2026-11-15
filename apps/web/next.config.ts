import type { NextConfig } from "next";

const nextConfig: NextConfig = { distDir: "build-output", experimental: { cpus: 1 } };
export default nextConfig;
