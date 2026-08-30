import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export (Firebase Hosting free tier) — app là client components thuần,
  // dữ liệu chỉ đến từ API (backend Cloud Run xác thực). Không cần Node server.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
