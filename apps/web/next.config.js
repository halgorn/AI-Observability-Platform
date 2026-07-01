/** @type {import('next').NextConfig} */
const nextConfig = {
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",

  async rewrites() {
    const queryUrl = process.env.QUERY_API_URL || "http://localhost:8001";
    const replayUrl = process.env.REPLAY_ENGINE_URL || "http://localhost:8002";
    return [
      // Proxy query-api calls through Next.js server (no CORS, no NEXT_PUBLIC)
      {
        source: "/api/query/:path*",
        destination: `${queryUrl}/:path*`,
      },
      // Proxy replay-engine calls through Next.js server (no CORS, no NEXT_PUBLIC)
      {
        source: "/api/replay/:path*",
        destination: `${replayUrl}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
