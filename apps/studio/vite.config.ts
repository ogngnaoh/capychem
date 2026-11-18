import { defineConfig } from "vite";
export default defineConfig({
  base: "/",
  cacheDir: ".vite",
  resolve: { dedupe: ["react", "react-dom"] },
  server: {
    host: "127.0.0.1",
    port: 5181,
    proxy: {
      "/api": {
        target: process.env.CAPYCHEM_API_URL || "http://127.0.0.1:8001",
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      onwarn(warning, warn) {
        if (
          warning.code === "MODULE_LEVEL_DIRECTIVE" &&
          warning.message.includes("use client")
        )
          return;
        warn(warning);
      },
    },
  },
});
