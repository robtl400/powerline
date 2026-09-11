/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["DM Sans", "sans-serif"],
      },
      colors: {
        /* CSS-variable tokens used by the base layer */
        border: "hsl(var(--border))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        /* Brand palette tokens — bg-brand-gum, text-brand-orange, etc. */
        "brand-orange":     "#F2542D",
        "brand-gum":        "#B05357",
        "brand-black":      "#111111",
        "brand-grey-dark":  "#53565B",
        "brand-grey-light": "#92918F",
        "brand-grey-mid":   "#D1D3D9",
        "page-bg":          "#F4F5F7",
        "brand-border":     "#E4E6EC",
      },
      borderRadius: {
        card: "10px",
        control: "7px",
        field: "8px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
      },
    },
  },
  plugins: [],
};
