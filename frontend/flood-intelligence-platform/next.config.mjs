import path from 'node:path';
import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'),
  allowedDevOrigins: ['127.0.0.1'],
  experimental: { optimizePackageImports: ['lucide-react'] },
  webpack(config) {
    config.module.rules.push({ test: /\.geojson$/, type: 'json' });
    return config;
  },
};
export default nextConfig;
