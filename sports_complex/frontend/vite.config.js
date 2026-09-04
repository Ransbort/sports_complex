import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// Builds straight into this Frappe app's own public/ directory (served at
// /assets/sports_complex/portal/... with zero extra hosting/deploy step -
// same as every hand-written JS file already under public/js) rather than
// a separate frontend deployment. Fixed (non-hashed) output filenames so
// www/portal/index.html can reference them directly without parsing
// Vite's manifest.json server-side - simplest thing that works for a
// first pass; revisit if cache-busting on redeploy becomes a problem.
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  base: '/assets/sports_complex/portal/',
  build: {
    outDir: '../public/portal',
    // false: this folder isn't exclusively Vite's - avoid it trying (and
    // sometimes failing, depending on filesystem permissions) to wipe
    // the whole directory on every build. Fixed output filenames mean a
    // rebuild just overwrites the same two files in place anyway.
    emptyOutDir: false,
    rollupOptions: {
      // Named "main" explicitly - left to its default, Vite names the
      // entry chunk after index.html ("index"), which doesn't match the
      // main.js/main.css filenames www/portal/index.html references.
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
      },
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
  server: {
    port: 8090,
  },
})
