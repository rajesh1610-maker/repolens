import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        accent: {
          DEFAULT: "#0f766e",
          fg: "#ffffff",
        },
      },
    },
  },
  plugins: [],
};

export default config;
