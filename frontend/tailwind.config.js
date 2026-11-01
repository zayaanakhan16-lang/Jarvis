/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Dark navy foundation
        navy: {
          950: '#050b16',
          900: '#071022',
          850: '#0a1729',
          800: '#0d1d33',
          700: '#122743',
        },
        // Charcoal surfaces
        charcoal: {
          900: '#11151c',
          850: '#161b24',
          800: '#1b212c',
          700: '#242c39',
          600: '#2f3947',
        },
        // Cyan / teal accents
        accent: {
          DEFAULT: '#22d3ee',
          bright: '#67e8f9',
          deep: '#0891b2',
          teal: '#2dd4bf',
        },
        state: {
          idle: '#64748b',
          running: '#22d3ee',
          queued: '#a78bfa',
          waiting: '#fbbf24',
          completed: '#34d399',
          failed: '#f87171',
          unavailable: '#475569',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderColor: {
        DEFAULT: 'rgba(148, 163, 184, 0.14)',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -12px rgba(0,0,0,0.6)',
        glow: '0 0 0 1px rgba(34,211,238,0.22), 0 8px 32px -12px rgba(34,211,238,0.35)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.22s ease-out',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
