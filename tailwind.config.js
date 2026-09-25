/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./apps/**/templates/**/*.html",
    "./templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff5ff",
          100: "#dbe8fe",
          200: "#bfd7fe",
          300: "#93bbfd",
          400: "#6094fa",
          500: "#3b70f6",
          600: "#1558b0",
          700: "#1a47a0",
          800: "#1b3d82",
          900: "#1c376b",
          950: "#152347",
        },
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Inter",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
      },
    },
  },
  plugins: [],
};
