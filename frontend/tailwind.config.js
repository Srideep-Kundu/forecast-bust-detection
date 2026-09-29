/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pine: {
          900: '#1f2a1d',
          800: '#2d3a2a',
          700: '#2a3827',
          600: '#3d5638',
          500: '#336443',
          400: '#4b5b47',
          300: '#85AB8B',
          100: '#eef4ed',
          50: '#f6f9f5',
        }
      },
      fontFamily: {
        sans: [
          'Neue Haas Grotesk Display Pro 55 Roman',
          'Neue Haas Grotesk Text Pro',
          'Helvetica Neue',
          'Helvetica',
          'Arial',
          'sans-serif',
        ],
        mono: [
          'IBM Plex Mono',
          'ui-monospace',
          'monospace',
        ],
      },
    },
  },
  plugins: [],
}
