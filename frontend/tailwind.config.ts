import type { Config } from "tailwindcss";

/**
 * VERITENSOR design tokens.
 * Dark infrastructure aesthetic: deep charcoal surfaces, hairline borders,
 * a single restrained cyan accent. No neon, no gradients-as-decoration.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: { DEFAULT: "#0A0C10", subtle: "#0E1116" },
        surface: { 1: "#12161D", 2: "#171C24", 3: "#1C222C" },
        line: { DEFAULT: "#1E252F", strong: "#2A323D", hi: "#3A4552" },
        ink: { 1: "#F0F3F6", 2: "#99A2AF", 3: "#5E6773" },
        accent: { DEFAULT: "#7DD6FA", dim: "#7DD6FA26", deep: "#3EA8D6" },
        mint: "#A8F0C6",
        positive: "#8FE3A9",
        warning: "#EFC468",
        negative: "#F27E88",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px", letterSpacing: "0.08em" }],
        xs: ["11px", { lineHeight: "16px" }],
      },
      borderRadius: { xs: "4px", sm: "6px", md: "8px", lg: "10px", xl: "12px" },
      boxShadow: {
        card: "0 4px 16px rgba(0,0,0,0.24)",
        pop: "0 8px 30px rgba(0,0,0,0.35)",
      },
      keyframes: {
        pulseDot: {
          "0%,100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.35", transform: "scale(0.85)" },
        },
        sweep: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(320%)" } },
        fadeUp: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-dot": "pulseDot 2s ease-in-out infinite",
        sweep: "sweep 2.4s linear infinite",
        "fade-up": "fadeUp 260ms cubic-bezier(0.4,0,0.2,1)",
      },
    },
  },
  plugins: [],
};
export default config;
