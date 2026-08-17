import { NextResponse } from 'next/server'
import { createClient, createServiceClient } from '@/lib/supabase/server'
import { createTrokeKey } from '@/lib/troke'

export async function POST(request: Request) {
  const authed = await createClient()
  const supabase = createServiceClient()

  const { data: { user } } = await authed.auth.getUser()

  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const body = await request.json().catch(() => ({}))
  const label = (body.label ?? '').trim()
  if (!label || label.length > 50) {
    return NextResponse.json({ error: 'Label must be 1–50 characters' }, { status: 422 })
  }

  let rawKey: string
  try {
    rawKey = await createTrokeKey()
  } catch {
    return NextResponse.json({ error: 'Failed to create key' }, { status: 502 })
  }

  const { data: keyRow, error: dbError } = await supabase
    .from('api_keys')
    .insert({ user_id: user.id, label, raw_key: rawKey })
    .select('id, label, created_at')
    .single()

  if (dbError) {
    return NextResponse.json({ error: 'Database error' }, { status: 500 })
  }

  return NextResponse.json({ ...keyRow, raw_key: rawKey }, { status: 201 })
}
