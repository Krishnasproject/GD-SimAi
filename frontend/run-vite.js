import { createServer } from 'vite'

async function run() {
  const server = await createServer({
    server: { port: 5173 },
  })
  await server.listen()
  server.printUrls()
}
run()
