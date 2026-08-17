// frontend/tailwind.config.ts
import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg:     { DEFAULT: '#0a0a0f', card: '#0d1520', sidebar: '#070d18' },
        border: { DEFAULT: '#1a3a6e', subtle: '#1a2a4a' },
        accent: { DEFAULT: '#1a6fff', soft: '#4d9fff', muted: '#6b8ab0' },
      },
      fontFamily: {
        outfit: ['var(--font-outfit)', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
export default config
