import { Router, type Request, type Response, type Router as RouterType } from "express";

const GOPRO_IP = process.env.GOPRO_IP ?? "10.5.5.9";
const GOPRO_BASE_URL = `http://${GOPRO_IP}:8080`;

const router: RouterType = Router();

async function proxyGet(
  goProPath: string,
  _req: Request,
  res: Response,
): Promise<void> {
  try {
    const url = `${GOPRO_BASE_URL}${goProPath}`;
    const response = await fetch(url, {
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) {
      res.status(response.status).json({ error: `GoPro returned ${response.status}` });
      return;
    }
    const data = await response.json();
    res.status(response.status).json(data);
  } catch (err) {
    res.status(502).json({
      error: "Camera not reachable",
      detail: String(err),
    });
  }
}

// GET /state -> /gopro/camera/state
router.get("/state", async (req, res) => {
  await proxyGet("/gopro/camera/state", req, res);
});

// GET /shutter/:action -> /gopro/camera/shutter/{start|stop}
router.get("/shutter/:action", async (req, res) => {
  const action = req.params.action;
  if (action !== "start" && action !== "stop") {
    res.status(400).json({ error: "Invalid action. Use 'start' or 'stop'." });
    return;
  }
  await proxyGet(`/gopro/camera/shutter/${action}`, req, res);
});

// GET /presets/set_group?id=N -> /gopro/camera/presets/set_group?id=N
router.get("/presets/set_group", async (req, res) => {
  const id = req.query.id;
  if (id === undefined || typeof id !== "string") {
    res.status(400).json({ error: "Missing required query parameter 'id'." });
    return;
  }
  await proxyGet(`/gopro/camera/presets/set_group?id=${id}`, req, res);
});

// GET /stream/:action -> /gopro/camera/stream/{start|stop}
router.get("/stream/:action", async (req, res) => {
  const action = req.params.action;
  if (action !== "start" && action !== "stop") {
    res.status(400).json({ error: "Invalid action. Use 'start' or 'stop'." });
    return;
  }
  await proxyGet(`/gopro/camera/stream/${action}`, req, res);
});

// GET /keep_alive -> /gopro/camera/keep_alive
router.get("/keep_alive", async (req, res) => {
  await proxyGet("/gopro/camera/keep_alive", req, res);
});

export { router as goProRouter, GOPRO_IP, GOPRO_BASE_URL };
