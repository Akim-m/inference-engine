import { NextResponse } from 'next/server'
import { createClient, createServiceClient } from '@/lib/supabase/server'
import { revokeTrokeKey } from '@/lib/troke'

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const authed = await createClient()
  const service = createServiceClient()

  const { data: { user } } = await authed.auth.getUser()
  if (!user) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const { data: keyRow, error: fetchError } = await service
    .from('api_keys')
    .select('id, raw_key, user_id, revoked_at')
    .eq('id', id)
    .single()

  if (fetchError || !keyRow) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  if (keyRow.user_id !== user.id) {
    return NextResponse.json({ error: 'Not found' }, { status: 404 })
  }

  if (keyRow.revoked_at) {
    return NextResponse.json({ error: 'Already revoked' }, { status: 409 })
  }

  try {
    await revokeTrokeKey(keyRow.raw_key)
  } catch {
    return NextResponse.json({ error: 'Failed to revoke key' }, { status: 502 })
  }

  const { error: updateError } = await service
    .from('api_keys')
    .update({ revoked_at: new Date().toISOString() })
    .eq('id', id)

  if (updateError) {
    return NextResponse.json({ error: 'Failed to update revocation status' }, { status: 500 })
  }

  return new NextResponse(null, { status: 204 })
}
