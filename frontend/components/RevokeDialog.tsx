'use client'

interface Props {
  onConfirm: () => void
  onCancel: () => void
}

export default function RevokeDialog({ onConfirm, onCancel }: Props) {
  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 px-4">
      <div className="bg-[#0d1520] border border-[#1a3a6e] rounded-lg w-full max-w-sm p-6 text-center">
        <h2 className="text-white font-bold text-lg mb-2">Revoke this key?</h2>
        <p className="text-[#6b8ab0] text-sm mb-6">
          This is permanent. Any application using this key will stop working immediately.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onConfirm}
            className="flex-1 bg-red-600 text-white text-sm font-semibold py-2 rounded-md hover:bg-red-700 transition-colors"
          >
            Revoke Key
          </button>
          <button
            onClick={onCancel}
            className="flex-1 border border-[#1a3a6e] text-[#6b8ab0] text-sm py-2 rounded-md hover:text-white transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
