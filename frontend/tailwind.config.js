/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /* All colors resolve to CSS variables defined in index.css (dark in
           :root, light under [data-theme="light"]), so flipping the theme
           re-skins the whole app. Solid tokens use the rgb(var(--x) /
           <alpha-value>) pattern so Tailwind /opacity utilities keep working;
           alpha-baked tokens (borders, *-soft, *-ring) are full-color vars. */
        bg: {
          DEFAULT: 'rgb(var(--bg-default) / <alpha-value>)',   // page void
          elev:    'rgb(var(--bg-elev) / <alpha-value>)',      // chrome (sidebar, topbar)
          surface: 'rgb(var(--bg-surface) / <alpha-value>)',   // panel surface
          card:    'rgb(var(--bg-card) / <alpha-value>)',      // nested card
          hover:   'rgb(var(--bg-hover) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'var(--border-default)',  // hairline default
          strong:  'var(--border-strong)',
          accent:  'var(--border-accent)',
        },
        text: {
          primary:   'rgb(var(--text-primary) / <alpha-value>)',
          secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
          tertiary:  'rgb(var(--text-tertiary) / <alpha-value>)',
          muted:     'rgb(var(--text-muted) / <alpha-value>)',
        },
        bull: { DEFAULT: 'rgb(var(--bull) / <alpha-value>)', soft: 'var(--bull-soft)', ring: 'var(--bull-ring)' },
        bear: { DEFAULT: 'rgb(var(--bear) / <alpha-value>)', soft: 'var(--bear-soft)', ring: 'var(--bear-ring)' },
        neut: { DEFAULT: 'rgb(var(--neut) / <alpha-value>)', soft: 'var(--neut-soft)', ring: 'var(--neut-ring)' },
        gold: { DEFAULT: 'rgb(var(--gold) / <alpha-value>)', bright: 'rgb(var(--gold-bright) / <alpha-value>)', soft: 'var(--gold-soft)' },
        accent: {
          blue:   'rgb(var(--accent-blue) / <alpha-value>)',
          cyan:   'rgb(var(--accent-cyan) / <alpha-value>)',
          purple: 'rgb(var(--accent-purple) / <alpha-value>)',
          pink:   'rgb(var(--accent-pink) / <alpha-value>)',
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
