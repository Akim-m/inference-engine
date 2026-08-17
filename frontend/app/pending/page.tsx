import Link from 'next/link'

export default function PendingPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center px-6">
      <div className="max-w-md w-full text-center">
        <Link href="/" className="text-white font-extrabold tracking-tight text-lg block mb-10">troke</Link>
        <div className="text-[#4d9fff] text-4xl mb-4">⏳</div>
        <h1 className="text-white text-2xl font-bold mb-3">Application under review</h1>
        <p className="text-[#6b8ab0] text-sm leading-relaxed">
          Your application is being reviewed. We'll send you an email when you're approved.
          Typical review time is 1–2 business days.
        </p>
      </div>
    </div>
  )
}
