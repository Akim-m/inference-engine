'use client'

import { useState } from 'react'

interface Props {
  onClose: () => void
  onCreated: (key: { id: string; label: string; raw_key: string; created_at: string }) => void
}

export default function NewKeyModal({ onClose, onCreated }: Props) {
  const [label, setLabel] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [createdKey, setCreatedKey] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  async function handleCreate() {
    setError('')
    setLoading(true)

    const res = await fetch('/api/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label }),
    })

    setLoading(false)

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      setError(data.error ?? 'Failed to create key')
      return
    }

    const data = await res.json()
    setCreatedKey(data.raw_key)
    onCreated({ id: data.id, label: data.label, raw_key: data.raw_key, created_at: data.created_at })
  }

  async function copyKey() {
    if (!createdKey) return
    await navigator.clipboard.writeText(createdKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 px-4">
      <div className="bg-[#0d1520] border border-[#1a3a6e] rounded-lg w-full max-w-md p-6">
        {!createdKey ? (
          <>
            <h2 className="text-white font-bold text-lg mb-1">Create API Key</h2>
            <p className="text-[#6b8ab0] text-sm mb-5">Give this key a label to identify it later.</p>

            <label className="text-[#6b8ab0] text-xs uppercase tracking-wider block mb-1">Label</label>
            <input
              autoFocus
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Production, Staging"
              maxLength={50}
              className="w-full bg-[#070d18] border border-[#1a3a6e] rounded-md px-3 py-2 text-white text-sm focus:outline-none focus:border-[#1a6fff] mb-4"
            />

            {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

            <div className="flex gap-3">
              <button
                onClick={handleCreate}
                disabled={!label.trim() || loading}
                className="flex-1 bg-[#1a6fff] text-white text-sm font-semibold py-2 rounded-md hover:bg-blue-600 transition-colors disabled:opacity-50"
              >
                {loading ? 'Creating...' : 'Create Key'}
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 text-[#6b8ab0] border border-[#1a3a6e] rounded-md text-sm hover:text-white transition-colors"
              >
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <h2 className="text-white font-bold text-lg mb-1">Key created</h2>
            <p className="text-amber-400 text-sm mb-4">
              Copy this key now. It will not be shown again.
            </p>

            <div className="bg-[#070d18] border border-[#1a3a6e] rounded-md px-3 py-3 font-mono text-sm text-[#4d9fff] break-all mb-4">
              {createdKey}
            </div>

            <div className="flex gap-3">
              <button
                onClick={copyKey}
                className="flex-1 bg-[#1a6fff] text-white text-sm font-semibold py-2 rounded-md hover:bg-blue-600 transition-colors"
              >
                {copied ? '✓ Copied' : 'Copy to Clipboard'}
              </button>
              <button
                onClick={onClose}
                className="px-4 py-2 text-[#6b8ab0] border border-[#1a3a6e] rounded-md text-sm hover:text-white transition-colors"
              >
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
