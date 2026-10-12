/// <reference types="vite/client" />

declare const __GAM_CHANNEL_CODE__: string;

interface ImportMetaEnv {
  /** C端用户服务（ruoyi-app）基础地址 */
  readonly VITE_APP_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
