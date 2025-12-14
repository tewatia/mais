export function getApiBaseUrl(): string {
  const fromEnv = (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? '';
  const trimmed = fromEnv.trim();
  if (!trimmed) return '';
  return trimmed.endsWith('/') ? trimmed.slice(0, -1) : trimmed;
}


