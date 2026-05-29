/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#070b14',
          elev: '#0b1220',
          surface: '#0f1729',
          card: '#121b30',
          hover: '#172240',
        },
        border: {
          DEFAULT: '#1c2745',
          strong: '#2a3a5e',
          accent: 'rgba(212,175,55,0.32)',
        },
        text: {
          primary: '#eef2f9',
          secondary: '#aebccf',
          tertiary: '#6b809e',
          muted: '#4a5b78',
        },
        bull: { DEFAULT: '#10d997', soft: 'rgba(16,217,151,0.12)', ring: 'rgba(16,217,151,0.35)' },
        bear: { DEFAULT: '#ff4d6d', soft: 'rgba(255,77,109,0.12)', ring: 'rgba(255,77,109,0.35)' },
        neut: { DEFAULT: '#f5a623', soft: 'rgba(245,166,35,0.12)', ring: 'rgba(245,166,35,0.35)' },
        gold: { DEFAULT: '#d4af37', bright: '#f0cf5f', soft: 'rgba(212,175,55,0.12)' },
        accent: {
          blue: '#4d8eff',
          cyan: '#22d3ee',
          purple: '#a78bfa',
          pink: '#f472b6',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"Barlow Condensed"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', { lineHeight: '14px' }],
        '3xs': ['9px', { lineHeight: '12px' }],
      },
      keyframes: {
        'flash-up': { '0%': { background: 'rgba(16,217,151,0.35)' }, '100%': { background: 'transparent' } },
        'flash-dn': { '0%': { background: 'rgba(255,77,109,0.35)' }, '100%': { background: 'transparent' } },
        'pulse-soft': { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.55' } },
        'fade-in': { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        shimmer: { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: {
        'flash-up': 'flash-up 1.2s ease-out',
        'flash-dn': 'flash-dn 1.2s ease-out',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
        'fade-in': 'fade-in 0.32s ease-out',
        shimmer: 'shimmer 2.4s linear infinite',
      },
    },
  },
  plugins: [],
};
