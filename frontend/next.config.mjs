/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

// On a hosted deployment (Vercel) the API cannot be on localhost. Fail loudly
// at build time rather than shipping a dashboard whose every request 502s.
if (process.env.NODE_ENV === "production" && !process.env.BACKEND_URL) {
  console.warn(
    "\n\u001b[33m[veritensor]\u001b[0m BACKEND_URL is not set.\n" +
    "  The frontend proxies /api/* to the VERITENSOR backend. Without a public\n" +
    "  backend URL every API call will fail once deployed.\n" +
    "  Set BACKEND_URL in your hosting provider's environment variables,\n" +
    "  e.g. BACKEND_URL=https://veritensor-api.onrender.com\n" +
    "  See docs/DEPLOYMENT.md.\n",
  );
}

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // The browser only ever talks to the Next server; the API key-free backend is
  // reached through this server-side proxy, so no backend URL is shipped to the
  // client and CORS never applies in the browser.
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/backend-health", destination: `${backend}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
        ],
      },
    ];
  },
};

export default nextConfig;
