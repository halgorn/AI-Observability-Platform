/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || "",
  experimental: {
    typedRoutes: false,
    trustHostHeader: true,
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_QUERY_URL: process.env.NEXT_PUBLIC_QUERY_URL || "http://localhost:8001",
    NEXT_PUBLIC_REPLAY_URL: process.env.NEXT_PUBLIC_REPLAY_URL || "http://localhost:8002",
  },
};

export default nextConfig;
