import { createServer } from 'vite';

let vite;
let restoreWindow;

async function frontendServer() {
  vite ??= await createServer({
    appType: 'custom',
    logLevel: 'silent',
    server: { middlewareMode: true },
  });
  return vite;
}

export async function loadFrontendModule(path) {
  return (await frontendServer()).ssrLoadModule(path);
}

export function createScriptedPyWebViewBridge(script = {}) {
  restoreWindow?.();
  const queues = new Map(
    Object.entries(script).map(([method, entries]) => [method, [...entries]]),
  );
  const calls = [];
  const api = new Proxy({}, {
    get(_target, property) {
      if (typeof property !== 'string') return undefined;
      if (property === 'then') return undefined;
      return async (...args) => {
        calls.push({ method: property, args });
        const queue = queues.get(property);
        if (!queue?.length) throw new Error(`No scripted PyWebView response for ${property}`);
        const entry = queue.shift();
        if ('reject' in entry) throw entry.reject;
        return typeof entry.resolve === 'function'
          ? entry.resolve(...args)
          : entry.resolve;
      };
    },
  });

  const previousWindow = globalThis.window;
  const bridgeWindow = new EventTarget();
  bridgeWindow.pywebview = { api };
  globalThis.window = bridgeWindow;
  restoreWindow = () => {
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  };

  return { api, calls, window: bridgeWindow };
}

export async function closeFrontendHarness() {
  restoreWindow?.();
  restoreWindow = undefined;
  await vite?.close();
  vite = undefined;
}
