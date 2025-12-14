import { getApiBaseUrl } from './baseUrl';

export type ApiError = { message: string };

async function parseError(resp: Response): Promise<ApiError> {
  try {
    const data = (await resp.json()) as unknown;
    if (
      typeof data === 'object' &&
      data !== null &&
      'error' in data &&
      typeof (data as any).error?.message === 'string'
    ) {
      return { message: (data as any).error.message };
    }
    if (
      typeof data === 'object' &&
      data !== null &&
      'detail' in data &&
      typeof (data as any).detail === 'string'
    ) {
      return { message: (data as any).detail };
    }
  } catch {
    // ignore
  }
  return { message: `Request failed (${resp.status})` };
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBaseUrl();
  const url = `${base}${path}`;
  const resp = await fetch(url, {
    ...init,
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });

  if (!resp.ok) {
    const err = await parseError(resp);
    throw new Error(err.message);
  }
  return (await resp.json()) as T;
}


