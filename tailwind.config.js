/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    '**/templates/**/*.html',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f5ff',
          100: '#e0eaff',
          200: '#c7d9ff',
          300: '#a4bfff',
          400: '#799cff',
          500: '#5475ff',
          600: '#3a49f5',
          700: '#2f3ae0',
          800: '#2832b5',
          900: '#252e8f',
        },
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}

