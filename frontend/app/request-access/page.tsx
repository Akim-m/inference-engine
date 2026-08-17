'use client'

import { useState } from 'react'
import Link from 'next/link'
import { createClient } from '@/lib/supabase/client'

const ROLES = ['Engineer', 'Product', 'Clinical', 'Executive', 'Other']

export default function RequestAccessPage() {
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    company: '',
    role: 'Engineer',
    use_case: '',
    password: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)

    const { error: signUpError } = await createClient().auth.signUp({
      email: form.email,
      password: form.password,
      options: {
        data: {
          full_name: form.full_name,
          company: form.company,
          role: form.role,
          use_case: form.use_case,
        },
      },
    })

    setLoading(false)

    if (signUpError) {
      setError(signUpError.message)
      return
    }

    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-6">
        <div className="max-w-md w-full text-center">
          <div className="text-[#4d9fff] text-4xl mb-4">✓</div>
          <h1 className="text-white text-2xl font-bold mb-3">Application received</h1>
          <p className="text-[#6b8ab0] text-sm leading-relaxed">
            We'll review your application and email you when you're approved.
            Typical review time is 1–2 business days.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-6 py-12">
      <div className="max-w-md w-full">
        <div className="mb-8">
          <Link href="/" className="text-white font-extrabold tracking-tight text-lg">troke</Link>
          <h1 className="text-white text-2xl font-bold mt-6 mb-1">Request access</h1>
          <p className="text-[#6b8ab0] text-sm">Enterprise access only. We review every application.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Full name</label>
            <input
              required
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            />
          </div>

          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Work email</label>
            <input
              required
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            />
          </div>

          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Company</label>
            <input
              required
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            />
          </div>

          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Role</label>
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            >
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>

          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">
              How do you plan to use Troke?
            </label>
            <textarea
              required
              rows={3}
              value={form.use_case}
              onChange={(e) => setForm({ ...form, use_case: e.target.value })}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff] resize-none"
            />
          </div>

          <div>
            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Password</label>
            <input
              required
              type="password"
              minLength={8}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-full bg-[#0d1520] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff]"
            />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-[#1a6fff] text-white font-semibold py-2.5 rounded-md hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Submitting...' : 'Submit Application'}
          </button>

          <p className="text-center text-[#6b8ab0] text-xs">
            Already have access?{' '}
            <Link href="/login" className="text-[#4d9fff] hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
