import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    // nén gzip làm Next gom các event SSE khi proxy /api/v1 sang Core nên chat mất realtime
    compress: false,
    async rewrites() {
        const backendUrl = process.env.BACKEND_URL || "http://localhost:3050";
        return [
            {
                source: "/api/v1/:path*",
                destination: `${backendUrl}/api/v1/:path*`,
            },
        ];
    },
    allowedDevOrigins: ["*.day-la-hiep.site"],
};

export default nextConfig;
