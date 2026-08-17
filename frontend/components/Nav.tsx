'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function Nav() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24)
    window.addEventListener('scroll', handler, { passive: true })
    return () => window.removeEventListener('scroll', handler)
  }, [])

  return (
    <nav
      className={`sticky top-0 z-40 flex items-center justify-between px-6 py-4 transition-all duration-300 ${
        scrolled ? 'nav-glass' : 'border-b border-transparent bg-transparent'
      }`}
    >
      <Link href="/" className="text-white font-outfit font-extrabold text-lg tracking-tight hover:text-[#4d9fff] transition-colors">
        troke
      </Link>
      <div className="flex items-center gap-6">
        <Link href="/docs" className="text-[#6b8ab0] text-sm hover:text-white transition-colors duration-200">
          Docs
        </Link>
        <Link href="/login" className="text-[#6b8ab0] text-sm hover:text-white transition-colors duration-200">
          Sign In
        </Link>
        <Link
          href="/request-access"
          className="btn-shimmer text-white text-sm font-semibold px-4 py-2 rounded-md"
        >
          Request Access
        </Link>
      </div>
    </nav>
  )
}
