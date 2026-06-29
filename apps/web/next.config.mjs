/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    typedRoutes: false,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_QUERY_URL: process.env.NEXT_PUBLIC_QUERY_URL || "http://localhost:8001",
    NEXT_PUBLIC_REPLAY_URL: process.env.NEXT_PUBLIC_REPLAY_URL || "http://localhost:8002",
  },
};

export default nextConfig;
