'use client'

import { useEffect, useState } from 'react'

interface Heading {
  text: string
  slug: string
  level: number
}

export default function DocsSidebar({ headings }: { headings: Heading[] }) {
  const [active, setActive] = useState('')

  useEffect(() => {
    const els = headings
      .map((h) => document.getElementById(h.slug))
      .filter((el): el is HTMLElement => el !== null)

    const obs = new IntersectionObserver(
      (entries) => {
        const hit = entries.find((e) => e.isIntersecting)
        if (hit) setActive(hit.target.id)
      },
      { rootMargin: '-10% 0px -75% 0px', threshold: 0 }
    )

    els.forEach((el) => obs.observe(el))
    return () => obs.disconnect()
  }, [headings])

  return (
    <aside className="hidden lg:block w-52 flex-shrink-0">
      <div className="sticky top-24">
        <p className="text-[#4a5568] text-xs font-semibold uppercase tracking-wider mb-4">Contents</p>
        <nav className="space-y-0.5">
          {headings.map((h) => (
            <a
              key={h.slug}
              href={`#${h.slug}`}
              className={`block text-xs py-1.5 border-l-2 transition-all duration-150 ${
                h.level === 3 ? 'pl-5' : 'pl-3'
              } ${
                active === h.slug
                  ? 'text-[#4d9fff] border-[#1a6fff]'
                  : 'text-[#4a5568] border-transparent hover:text-[#6b8ab0] hover:border-[#1a3a6e]'
              }`}
            >
              {h.text}
            </a>
          ))}
        </nav>
      </div>
    </aside>
  )
}
