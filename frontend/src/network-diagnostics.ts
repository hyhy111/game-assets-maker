interface NetworkFailure {
  method: string;
  url: string;
  http_status?: number;
  code?: number;
  error_type: string;
  message: string;
  stack?: string;
  retried?: boolean;
}

type Reporter = (details: NetworkFailure) => Promise<unknown>;
const pending: NetworkFailure[] = [];
let listeningWindow: Window | undefined;

function flush() {
  try {
    const reporter = (window as Window & { pywebview?: { api?: { report_network_error?: Reporter } } }).pywebview?.api?.report_network_error;
    if (!reporter) return;
    for (const report of pending.splice(0)) {
      try { void Promise.resolve(reporter(report)).catch(() => {}); } catch { /* Preserve the request error. */ }
    }
  } catch { /* The bridge may not be ready yet. */ }
}

export function reportNetworkError(details: NetworkFailure, secrets: readonly string[] = []): void {
  if (typeof window === 'undefined') return;
  try {
    const sanitize = (value: string) => {
      value = String(value);
      for (const secret of [...secrets].filter(Boolean).sort((a, b) => b.length - a.length)) value = value.split(secret).join('[REDACTED]');
      return value.replace(/https?:\/\/[^\s"'<>]+/g, '[URL]').replace(/Bearer\s+[^\s,"'<>]+/gi, 'Bearer [REDACTED]').slice(0, 8000);
    };
    let endpoint = '[INVALID URL]';
    try {
      const url = new URL(details.url, 'http://localhost');
      url.username = ''; url.password = ''; url.search = ''; url.hash = '';
      endpoint = url.toString();
    } catch { /* Invalid endpoints are still useful network failures to record. */ }
    pending.push({ ...details, url: endpoint, message: sanitize(details.message), stack: details.stack ? sanitize(details.stack) : undefined });
    if (pending.length > 100) pending.shift();
    if (listeningWindow !== window) {
      listeningWindow?.removeEventListener('pywebviewready', flush);
      listeningWindow = window;
      window.addEventListener('pywebviewready', flush);
    }
    flush();
  } catch { /* Diagnostics are best effort and never trigger another HTTP request. */ }
}
