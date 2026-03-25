import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { AnalyticsTracker } from '@/components/admin/analytics-tracker'
import './globals.css'

const _geist = Geist({ subsets: ["latin"] });
const _geistMono = Geist_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: 'Metalyzi - AI-Powered Property Investment Analysis',
  description: 'Analyse any UK property deal in seconds. Get instant SDLT calculations, mortgage costs, rental yield, cash flow projections, and AI-powered investment insights.',
  keywords: ['property investment', 'UK property', 'SDLT calculator', 'rental yield', 'buy to let', 'property analysis'],
  icons: {
    icon: '/icon.svg',
    shortcut: '/icon.svg',
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className="dark">
      <body className="font-sans antialiased bg-background text-foreground">
        {children}
        <AnalyticsTracker />
        <Analytics />
      </body>
    </html>
  )
}
