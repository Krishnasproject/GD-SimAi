import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // Keep ONNX wasm artifacts out of dep optimization to avoid bad pre-bundle paths.
    // VAD libs should stay optimizable so CJS wrappers are transformed for browser use.
    exclude: ['ort-wasm-simd-threaded', 'ort-wasm-threaded', 'onnxruntime-web']
  },
})
