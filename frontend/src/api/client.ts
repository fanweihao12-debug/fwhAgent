const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;

interface RequestOptions extends RequestInit {
  bodyJson?: unknown;
}

export const requestJson = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const { bodyJson, headers, ...restOptions } = options;
  const hasJsonBody = bodyJson !== undefined;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...restOptions,
    headers: {
      ...(hasJsonBody ? { 'Content-Type': 'application/json' } : {}),
      ...headers
    },
    body: hasJsonBody ? JSON.stringify(bodyJson) : undefined
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `Request failed with status ${response.status}`);
  }

  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
};
