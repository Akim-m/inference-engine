'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface Props {
  company: string
}

export default function Sidebar({ company }: Props) {
  const pathname = usePathname()
  const router = useRouter()

  async function signOut() {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/')
    router.refresh()
  }

  const navItem = (href: string, label: string) => {
    const active = pathname === href
    return (
      <Link
        href={href}
        className={`block text-sm px-3 py-2 rounded-md transition-colors ${
          active
            ? 'bg-[#1a6fff18] text-[#4d9fff]'
            : 'text-[#6b8ab0] hover:text-white'
        }`}
      >
        {label}
      </Link>
    )
  }

  return (
    <aside className="w-48 bg-[#070d18] border-r border-[#1a2a4a] flex flex-col min-h-screen flex-shrink-0">
      <div className="px-4 py-5 border-b border-[#1a2a4a]">
        <Link href="/" className="text-white font-extrabold tracking-tight text-base">troke</Link>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItem('/dashboard', 'API Keys')}
        {navItem('/docs', 'Docs')}
      </nav>

      <div className="px-4 py-4 border-t border-[#1a2a4a]">
        <p className="text-[#6b8ab0] text-xs mb-2 truncate">{company}</p>
        <button
          onClick={signOut}
          className="text-[#6b8ab0] text-xs hover:text-white transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  )
}
