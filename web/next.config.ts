import type { NextConfig } from "next";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  output: "standalone",
  ...(basePath ? { basePath } : {}),
  async redirects() {
    return [
      { source: "/paper", destination: "/trades", permanent: false },
      { source: "/settings", destination: "/control", permanent: false },
    ];
  },
};

export default nextConfig;
