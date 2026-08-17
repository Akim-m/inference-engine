import { createTrokeKey, revokeTrokeKey } from '@/lib/troke'

const originalFetch = global.fetch

beforeEach(() => {
  process.env.TROKE_API_URL = 'http://fake-troke:8000'
  process.env.TROKE_ADMIN_KEY = 'test-admin-key'
})
afterEach(() => { global.fetch = originalFetch })

test('createTrokeKey calls POST /v1/admin/keys and returns key', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ key: 'sk-tr-abc123' }),
  } as Response)

  const key = await createTrokeKey()

  expect(global.fetch).toHaveBeenCalledWith(
    'http://fake-troke:8000/v1/admin/keys',
    expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-API-Key': 'test-admin-key' }),
    })
  )
  expect(key).toBe('sk-tr-abc123')
})

test('createTrokeKey throws on non-ok response', async () => {
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 500,
  } as Response)

  await expect(createTrokeKey()).rejects.toThrow('Troke key creation failed: 500')
})

test('revokeTrokeKey calls DELETE /v1/admin/keys/{key}', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true } as Response)

  await revokeTrokeKey('sk-tr-abc123')

  expect(global.fetch).toHaveBeenCalledWith(
    'http://fake-troke:8000/v1/admin/keys/sk-tr-abc123',
    expect.objectContaining({
      method: 'DELETE',
      headers: expect.objectContaining({ 'X-API-Key': 'test-admin-key' }),
    })
  )
})

test('revokeTrokeKey ignores 404 (already revoked)', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 404 } as Response)
  await expect(revokeTrokeKey('sk-tr-abc123')).resolves.toBeUndefined()
})

test('revokeTrokeKey throws on other errors', async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 500 } as Response)
  await expect(revokeTrokeKey('sk-tr-abc123')).rejects.toThrow('Troke key revocation failed: 500')
})
