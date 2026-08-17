interface Props {
  id: string
  label: string
  rawKey: string
  createdAt: string
  onRevoke: (id: string) => void
}

function maskKey(raw: string): string {
  if (raw.length <= 4) return '••••'
  return `sk-tr-${'•'.repeat(8)}${raw.slice(-4)}`
}

export default function KeyCard({ id, label, rawKey, createdAt, onRevoke }: Props) {
  const date = new Date(createdAt).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })

  return (
    <div className="card-hover bg-[#0d1520] border border-[#1a3a6e] rounded-lg px-5 py-4 flex items-center justify-between group">
      <div>
        <p className="text-white text-sm font-semibold mb-1">{label}</p>
        <p className="text-[#6b8ab0] text-xs font-mono group-hover:text-[#4d9fff] transition-colors duration-300">{maskKey(rawKey)}</p>
        <p className="text-[#4a5568] text-xs mt-1">Created {date}</p>
      </div>
      <button
        onClick={() => onRevoke(id)}
        className="text-red-400 text-xs border border-red-900 px-3 py-1.5 rounded hover:bg-red-950 hover:border-red-700 transition-all duration-200 opacity-60 group-hover:opacity-100"
      >
        Revoke
      </button>
    </div>
  )
}
