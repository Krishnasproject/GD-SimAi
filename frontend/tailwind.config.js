/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#121216',
        surface: '#1C1C21',
        surface2: '#25252A',
        ink: '#ffffff',
        border: '#333333',
        primary: '#2A9D8F',
        accent: '#2A9D8F',
        highlight: '#E9C46A',
        core: '#8d99ae',
        pro: '#2A9D8F',
        ai: '#E9C46A',
        enterprise: '#2b2d42',
        success: '#2A9D8F',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      boxShadow: {
        card: '0 10px 30px rgba(15, 23, 42, 0.06)',
        lift: '0 20px 45px rgba(15, 23, 42, 0.1)',
      },
      animation: {
        'blob': 'blob 7s infinite',
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite alternate',
        'float-slow': 'floatSlow 8s ease-in-out infinite',
      },
      keyframes: {
        blob: {
          '0%': { transform: 'translate(0px, 0px) scale(1)' },
          '33%': { transform: 'translate(30px, -50px) scale(1.1)' },
          '66%': { transform: 'translate(-20px, 20px) scale(0.9)' },
          '100%': { transform: 'translate(0px, 0px) scale(1)' },
        },
        pulseGlow: {
          '0%': { opacity: 0.8, boxShadow: '0 0 15px rgba(42, 157, 143, 0.2)' },
          '100%': { opacity: 1, boxShadow: '0 0 30px rgba(42, 157, 143, 0.4)' },
        },
        floatSlow: {
          '0%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-8px)' },
          '100%': { transform: 'translateY(0px)' },
        }
      }
    },
  },
  plugins: [],
}
