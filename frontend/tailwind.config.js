/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,ts,tsx}',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#FFBD5C',
          50: '#FFF8EB',
          100: '#FFEBCB',
          200: '#FFDA9A',
          300: '#FFC96F',
          400: '#FFC15F',
          500: '#FFBD5C',
          600: '#E89A2D',
          700: '#BE741B',
          800: '#8E4F16',
          900: '#5F3212',
        },
        success: {
          DEFAULT: '#2CC985',
          50: '#E6F9F0',
          100: '#B3EDD3',
          500: '#2CC985',
          600: '#25A86E',
        },
        danger: {
          DEFAULT: '#E74C3C',
          50: '#FCECEA',
          100: '#F7C5C0',
          500: '#E74C3C',
          600: '#C0392B',
        },
        warning: {
          DEFAULT: '#F39C12',
          50: '#FEF5E6',
          100: '#FCE3B3',
          500: '#F39C12',
          600: '#D68910',
        },
        accent: {
          DEFAULT: '#CB3F3E',
          50: '#FCEEEE',
          100: '#F7D1D0',
          500: '#CB3F3E',
          600: '#A93231',
        },
        dark: {
          bg: '#1A1A1A',
          surface: '#242424',
          border: '#333333',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
