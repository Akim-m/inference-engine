'use client'

import { useState } from 'react'
import KeyCard from '@/components/KeyCard'
import NewKeyModal from '@/components/NewKeyModal'
import RevokeDialog from '@/components/RevokeDialog'

interface Key {
  id: string
  label: string
  raw_key: string
  created_at: string
}

interface Props {
  initialKeys: Key[]
}

export default function KeysClient({ initialKeys }: Props) {
  const [keys, setKeys] = useState<Key[]>(initialKeys)
  const [showNew, setShowNew] = useState(false)
  const [revokeId, setRevokeId] = useState<string | null>(null)

  function handleKeyCreated(key: Key) {
    setKeys((prev) => [key, ...prev])
  }

  async function handleRevoke(id: string) {
    const res = await fetch(`/api/keys/${id}`, { method: 'DELETE' })
    if (res.ok) {
      setKeys((prev) => prev.filter((k) => k.id !== id))
    }
    setRevokeId(null)
  }

  return (
    <>
      <div className="flex items-center justify-between mb-6 animate-fade-up">
        <div>
          <h1 className="text-white text-xl font-bold">API Keys</h1>
          <p className="text-[#6b8ab0] text-sm mt-0.5">
            {keys.length} active {keys.length === 1 ? 'key' : 'keys'}
          </p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="btn-shimmer text-white text-sm font-semibold px-4 py-2 rounded-md"
        >
          + New Key
        </button>
      </div>

      {keys.length === 0 ? (
        <div className="text-center py-16 text-[#6b8ab0] text-sm animate-fade-in">
          No API keys yet. Create one to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {keys.map((k, i) => (
            <div key={k.id} className="key-item" style={{ animationDelay: `${i * 60}ms` }}>
              <KeyCard
                id={k.id}
                label={k.label}
                rawKey={k.raw_key}
                createdAt={k.created_at}
                onRevoke={(id) => setRevokeId(id)}
              />
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <NewKeyModal
          onClose={() => setShowNew(false)}
          onCreated={handleKeyCreated}
        />
      )}

      {revokeId && (
        <RevokeDialog
          onConfirm={() => handleRevoke(revokeId)}
          onCancel={() => setRevokeId(null)}
        />
      )}
    </>
  )
}
