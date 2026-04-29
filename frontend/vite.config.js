import { defineConfig } from 'vite'

export default defineConfig({
  base: '/',
  resolve: {
    alias: {
      vue: 'vue/dist/vue.esm-bundler.js'
    }
  },
  build: {
    outDir: 'dist'
  }
})
