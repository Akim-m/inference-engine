import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import Sidebar from '@/components/Sidebar'

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) redirect('/login')

  const { data: profile } = await supabase
    .from('profiles')
    .select('company')
    .eq('id', user.id)
    .single()

  return (
    <div className="flex min-h-screen bg-[#0a0a0f]">
      <Sidebar company={profile?.company ?? ''} />
      <main className="flex-1 p-8">
        {children}
      </main>
    </div>
  )
}
