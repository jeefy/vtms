/**
 * Playwright global teardown.
 *
 * Stops the Aedes broker and Vite dev server started in global-setup.
 */
export default async function globalTeardown() {
  const cleanup = (globalThis as any).__vtms_cleanup;
  if (!cleanup) return;

  const { aedesInstance, httpServer, viteProcess } = cleanup;

  // Kill Vite dev server
  if (viteProcess?.pid) {
    try {
      process.kill(viteProcess.pid, "SIGTERM");
    } catch {
      // already dead
    }
  }

  // Close Aedes broker
  if (aedesInstance) {
    await new Promise<void>((resolve) => aedesInstance.close(() => resolve()));
  }

  // Close HTTP/WS server
  if (httpServer) {
    await new Promise<void>((resolve) => httpServer.close(() => resolve()));
  }

  console.log("[global-teardown] All servers stopped");
}
