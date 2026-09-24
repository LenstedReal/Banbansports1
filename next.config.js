/** @type {import('next').NextConfig} */
// Vercel'de /api/* → vercel.json rewrites ile Python fonksiyonuna (api/index.py) gider.
// Yerel geliştirmede (next dev) /api/* ayrı çalışan FastAPI'ye (8001) proxy'lenir.
const backend = (!process.env.VERCEL && (process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_BACKEND_URL || '').trim()) || '';

const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**' },
      { protocol: 'http', hostname: '**' },
    ],
    formats: ['image/avif', 'image/webp'],
    minimumCacheTTL: 86400,
  },
  experimental: { scrollRestoration: true },
  async rewrites() {
    if (!backend) return [];
    return { beforeFiles: [{ source: '/api/:path*', destination: `${backend}/api/:path*` }] };
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Frame-Options', value: 'SAMEORIGIN' },
        ],
      },
      { source: '/icons/:path*', headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }] },
      { source: '/logos/:path*', headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }] },
      { source: '/brand/:path*', headers: [{ key: 'Cache-Control', value: 'public, max-age=31536000, immutable' }] },
    ];
  },
};

module.exports = nextConfig;
