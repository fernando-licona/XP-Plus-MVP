import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig({plugins:[react(),tailwindcss()],resolve:{dedupe:["react","react-dom"]},server:{host:"127.0.0.1",port:5100,strictPort:true,proxy:{"/xpp":{target:process.env.XPP_API_URL||"http://127.0.0.1:8765",changeOrigin:true}}}});
