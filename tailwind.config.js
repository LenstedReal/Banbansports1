/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{ts,tsx,js,jsx}',
    './components/**/*.{ts,tsx,js,jsx}',
    './lib/**/*.{ts,tsx,js,jsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          0: '#07070b',
          1: '#0d0d14',
          2: '#13131c',
        },
        accent: {
          cyan:   '#00f0ff',
          pink:   '#ff00aa',
          purple: '#aa00ff',
          green:  '#00ff88',
          orange: '#ff8800',
          amber:  '#ffaa00',
          red:    '#ff0040',
        },
        ink: {
          high: '#f4f1ff',
          mid: '#cfc9e0',
          low: '#9b8db5',
        },
        // P3 #99: text-neon-cyan utility — Scoreboard.tsx kullanıyordu ama theme'de yoktu
        neon: {
          cyan: '#00f0ff',
          pink: '#ff00aa',
          green: '#00ff88',
          orange: '#ff8800',
        },
      },
      fontFamily: {
        display: ['"Bebas Neue"', '"Oswald"', 'system-ui', 'sans-serif'],
        mono: ['"VT323"', '"IBM Plex Mono"', 'ui-monospace', 'monospace'],
        body: ['"Rajdhani"', '"Inter"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'neon-cyan': '0 0 24px rgba(0,212,255,0.35), 0 0 1px rgba(0,212,255,0.6) inset',
        'neon-pink': '0 0 24px rgba(255,46,136,0.35), 0 0 1px rgba(255,46,136,0.6) inset',
        'card': '0 8px 32px rgba(0,0,0,0.6), 0 1px 0 rgba(255,255,255,0.04) inset',
      },
      animation: {
        'pulse-slow': 'pulseSlow 2.4s ease-in-out infinite',
        'flash': 'flash .5s ease-out',
        'rise': 'rise .5s cubic-bezier(.34,1.56,.64,1)',
        'bb-toast-in': 'bbToastIn .25s ease-out',
      },
      keyframes: {
        pulseSlow: {
          '0%,100%': { opacity: '0.55' },
          '50%': { opacity: '1' },
        },
        flash: {
          '0%': { opacity: '0', transform: 'scale(.98)' },
          '50%': { opacity: '1' },
          '100%': { opacity: '0', transform: 'scale(1)' },
        },
        rise: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        bbToastIn: {
          '0%': { opacity: '0', transform: 'translateX(40px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
    },
  },
  plugins: [],
};
