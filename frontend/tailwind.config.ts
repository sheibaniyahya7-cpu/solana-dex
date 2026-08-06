import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark trading UI palette
        background: "#0a0a0f",
        surface: "#111118",
        "surface-2": "#1a1a24",
        "surface-3": "#22222e",
        border: "#2a2a38",
        "border-hover": "#3a3a4e",
        // Brand
        primary: "#6366f1",       // Indigo
        "primary-hover": "#4f46e5",
        accent: "#8b5cf6",        // Purple
        // Semantic
        success: "#10b981",       // Green — bullish
        warning: "#f59e0b",       // Amber — caution
        danger: "#ef4444",        // Red — bearish / rug
        info: "#3b82f6",          // Blue — info
        // Text
        "text-primary": "#f1f5f9",
        "text-secondary": "#94a3b8",
        "text-muted": "#475569",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-in-out",
        "slide-up": "slideUp 0.3s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(10px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
