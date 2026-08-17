'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    const { error: signInError } = await createClient().auth.signInWithPassword({ email, password })

    if (signInError) {
      setError('Invalid email or password.')
      setLoading(false)
      return
    }

    // Middleware will redirect to /pending if not approved
    router.push('/dashboard')
    router.refresh()
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-6">
      <div className="max-w-sm w-full">
        <div className="mb-8">
          <Link href="/" className="text-white font-extrabold tracking-tight text-lg">troke</Link>
          <h1 className="text-white text-2xl font-bold mt-6 mb-1">Sign in</h1>
          <p className="text-[#6b8ab0] text-sm">Access your API keys and dashboard.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Email</label>
            <input
              required
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            />
          </div>

          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Password</label>
            <input
              required
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#1a6fff] text-white font-semibold py-2.5 rounded-md hover:bg-blue-600 transition-colors disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>

          <p className="text-center text-[#6b8ab0] text-xs">
            No access yet?{' '}
            <Link href="/request-access" className="text-[#4d9fff] hover:underline">Request access</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
