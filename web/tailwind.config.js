/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          950: "#07090c",
          900: "#0b0e11",
          850: "#10151c",
          800: "#161c24",
          700: "#1e2631",
          600: "#2a3442",
        },
        mist: {
          100: "#e7ecf1",
          300: "#b4c0cc",
          500: "#8b98a5",
        },
        call: "#3dd68c",
        put: "#ff5d5d",
        amber: "#f5c14a",
        ice: "#4da3ff",
      },
    },
  },
  plugins: [],
};
