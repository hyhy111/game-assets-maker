import { httpPost } from './http';

// Vite embeds the packaging value; user data and runtime environment cannot override it.
export const CHANNEL_CODE = __GAM_CHANNEL_CODE__;
let startupReported = false;

export function reportStartup(): void {
  if (startupReported) return;
  startupReported = true;
  void httpPost('/app/channel/startup', { channelCode: CHANNEL_CODE }, {
    anonymous: true, noRecovery: true, timeoutMs: 5000,
  }).catch(() => {
    // Startup telemetry must never interrupt local processing or session recovery.
  });
}
