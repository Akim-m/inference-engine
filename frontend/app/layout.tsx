import type { Metadata } from 'next'
import { Outfit } from 'next/font/google'
import './globals.css'

const outfit = Outfit({
  subsets: ['latin'],
  variable: '--font-outfit',
  display: 'swap',
  weight: ['400', '600', '700', '800'],
})

export const metadata: Metadata = {
  title: 'troke | Medical AI Inference API',
  description: 'Structured medical image inference via a single REST API. Built for clinical software teams.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={outfit.variable}>
      <body className="bg-[#0a0a0f] text-white font-outfit antialiased min-h-screen">
        {children}
      </body>
    </html>
  )
}
