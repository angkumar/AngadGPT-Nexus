/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"] ,
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace']
      },
      colors: {
        obsidian: '#0B0D10',
        ember: '#FF5C35',
        cobalt: '#2A6BFF',
        haze: '#F4F1ED'
      },
      boxShadow: {
        glow: '0 0 30px rgba(42,107,255,0.35)'
      }
    }
  },
  plugins: []
}
