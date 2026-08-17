export async function createTrokeKey(): Promise<string> {
  const res = await fetch(`${process.env.TROKE_API_URL}/v1/admin/keys`, {
    method: 'POST',
    headers: { 'X-API-Key': process.env.TROKE_ADMIN_KEY! },
  })
  if (!res.ok) throw new Error(`Troke key creation failed: ${res.status}`)
  const { key } = await res.json()
  return key as string
}

export async function revokeTrokeKey(rawKey: string): Promise<void> {
  const res = await fetch(`${process.env.TROKE_API_URL}/v1/admin/keys/${rawKey}`, {
    method: 'DELETE',
    headers: { 'X-API-Key': process.env.TROKE_ADMIN_KEY! },
  })
  if (!res.ok && res.status !== 404)
    throw new Error(`Troke key revocation failed: ${res.status}`)
}
