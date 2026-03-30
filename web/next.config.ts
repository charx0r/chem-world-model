import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["@rdkit/rdkit"],
  turbopack: {},
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://api:8000/api/:path*",
      },
      {
        source: "/health",
        destination: "http://api:8000/health",
      },
    ];
  },
};

export default nextConfig;
