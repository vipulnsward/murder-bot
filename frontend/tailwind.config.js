/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        gold: { DEFAULT: "#e6c35c", bright: "#f7dd8f", deep: "#b8902f" },
        ember: { DEFAULT: "#e0553f", deep: "#a02a1c" },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        display: ['Georgia', '"Iowan Old Style"', 'serif'],
      },
      keyframes: {
        pulseGlow: { "0%,100%": { opacity: "0.8" }, "50%": { opacity: "1" } },
      },
      animation: { pulseGlow: "pulseGlow 2.6s ease-in-out infinite" },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
