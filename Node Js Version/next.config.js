
/** @type {import('next').NextConfig} */

const nextConfig = {
  output: 'standalone',
  // The "experimental.turbo: false" option was removed as it was causing a build error.
  // Turbopack is primarily invoked via the CLI for the dev server.
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'picsum.photos',
        port: '',
        pathname: '/**',
      },
      // Removed: cdn.dummyjson.com as it was for the example page
    ],
  },
};

export default nextConfig;
