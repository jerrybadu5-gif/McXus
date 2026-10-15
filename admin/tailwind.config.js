/** McXus staff console tokens: the app's navy and gold, Plus Jakarta Sans. Gold means "waiting for you". */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#0B2545", soft: "#13355E", line: "#1E4573", muted: "#C9D6E6" },
        gold: { DEFAULT: "#E9A23B", deep: "#B9771A", soft: "#FBEBD0", ink: "#6B4706" },
        ink: "#0E1B2B",
        body: "#263445",
        muted: "#556274",
        bg: "#F4F6F9",
        line: "#E2E7EE",
        tint: "#E8EEF6",
        late: { DEFAULT: "#B42318", soft: "#FDECEA" },
        ok: { DEFAULT: "#1B7F5A", soft: "#E3F3EC" },
      },
      fontFamily: { sans: ['"Plus Jakarta Sans"', "system-ui", "sans-serif"] },
      fontSize: { "2xs": ["11px", "16px"] },
    },
  },
  plugins: [],
};
