const rawApiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();

const normalizedApiBase = rawApiBase
  ? rawApiBase.replace(/\/+$/, '')
  : 'http://localhost:8000';

export const API_BASE_URL = normalizedApiBase;

export function apiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

export function wsUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const wsBase = API_BASE_URL.startsWith('https://')
    ? API_BASE_URL.replace('https://', 'wss://')
    : API_BASE_URL.replace('http://', 'ws://');
  return `${wsBase}${cleanPath}`;
}
