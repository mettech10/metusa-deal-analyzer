/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: '/admin/login',
        destination: '/admin/admin_login.html',
      },
      {
        source: '/admin/dashboard',
        destination: '/admin/admin_dashboard.html',
      },
    ]
  },
}

export default nextConfig
