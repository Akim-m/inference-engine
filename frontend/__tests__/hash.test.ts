import { sha256 } from '@/lib/hash'

test('sha256 produces correct hex digest', () => {
  // echo -n "hello" | sha256sum → 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
  expect(sha256('hello')).toBe(
    '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
  )
})

test('sha256 is deterministic', () => {
  expect(sha256('troke-test-key')).toBe(sha256('troke-test-key'))
})
