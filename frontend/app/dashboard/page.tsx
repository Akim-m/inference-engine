import { createClient, createServiceClient } from '@/lib/supabase/server'
import KeysClient from '@/components/KeysClient'

export default async function DashboardPage() {
  const authed = await createClient()
  const service = createServiceClient()

  const { data: { user } } = await authed.auth.getUser()

  const { data: keys } = await service
    .from('api_keys')
    .select('id, label, raw_key, created_at')
    .eq('user_id', user!.id)
    .is('revoked_at', null)
    .order('created_at', { ascending: false })

  return <KeysClient initialKeys={keys ?? []} />
}
