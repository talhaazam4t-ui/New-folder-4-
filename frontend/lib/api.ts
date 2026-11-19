/**
 * Standardized API Client for Talox Tech Stream.
 * Automatically injects Bearer token and X-Tenant-ID headers.
 */

import { clearActiveTenant, clearSession, getActiveTenant, getAuthToken } from "./auth";

export function getBackendUrl(): string {
  // 1. SSR / Next.js static export pre-render: never bake localhost into HTML/state
  if (typeof window === "undefined") {
    return "";
  }

  // 2. Browser runtime guardrail: non-local hostnames ALWAYS use same-origin relative URLs ("")
  //    even if NODE_ENV=development or NEXT_PUBLIC_BACKEND_URL=http://localhost:8000 was baked at build time.
  const hostname = window.location.hostname.toLowerCase();
  if (hostname !== "localhost" && hostname !== "127.0.0.1") {
    return "";
  }

  // 3. Local development (localhost / 127.0.0.1): preserve configured NEXT_PUBLIC_BACKEND_URL or dev default
  const configured = process.env.NEXT_PUBLIC_BACKEND_URL;
  if (configured !== undefined) {
    return configured.replace(/\/+$/, "");
  }

  return process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
}

// Legacy compatibility export (SSR-safe; prefer calling getBackendUrl() per request)
export const BACKEND_URL = getBackendUrl();

export interface ApiResponse<T = any> {
  success?: boolean;
  data?: T;
  message?: string;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  [key: string]: any;
}

function buildRequestHeaders(
  customHeaders?: HeadersInit,
  includeJsonContentType = true
): Record<string, string> {
  const token = getAuthToken();
  const tenant = getActiveTenant();

  const headers: Record<string, string> = {};
  if (includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }

  if (customHeaders) {
    if (customHeaders instanceof Headers) {
      customHeaders.forEach((value, key) => {
        headers[key] = value;
      });
    } else if (Array.isArray(customHeaders)) {
      for (const [key, value] of customHeaders) {
        headers[key] = value;
      }
    } else {
      Object.assign(headers, customHeaders);
    }
  }

  if (token && !headers["Authorization"] && !headers["authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (tenant?.id && !headers["X-Tenant-ID"] && !headers["x-tenant-id"]) {
    headers["X-Tenant-ID"] = tenant.id;
  }

  return headers;
}

function handleAuthOrTenantFailure(status: number, errorCode?: string): void {
  if (status === 401) {
    clearSession();
    if (typeof window !== "undefined" && !window.location.pathname.includes("/login")) {
      window.location.href = "/login";
    }
  } else if (status === 403 && errorCode === "TENANT_ISOLATION_VIOLATION") {
    clearActiveTenant();
    if (
      typeof window !== "undefined" &&
      !window.location.pathname.includes("/login") &&
      !window.location.pathname.includes("/onboarding") &&
      !window.location.pathname.includes("/admin")
    ) {
      window.location.href = "/onboarding";
    }
  }
}

export async function apiFetchResponse(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = buildRequestHeaders(options.headers, false);
  const url = endpoint.startsWith("http") ? endpoint : `${getBackendUrl()}${endpoint}`;

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    handleAuthOrTenantFailure(401);
  } else if (res.status === 403) {
    try {
      const cloned = res.clone();
      const errJson = await cloned.json();
      const errorCode = errJson?.error?.code || errJson?.detail?.code;
      handleAuthOrTenantFailure(403, errorCode);
    } catch {
      // Ignore non-JSON 403 bodies
    }
  }

  return res;
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const headers = buildRequestHeaders(options.headers, true);
  const url = endpoint.startsWith("http") ? endpoint : `${getBackendUrl()}${endpoint}`;

  try {
    const res = await fetch(url, {
      ...options,
      headers,
    });

    const rawText = await res.text();
    let data: any = {};
    if (rawText) {
      try {
        data = JSON.parse(rawText);
      } catch {
        data = {
          success: false,
          error: {
            code: `HTTP_${res.status}`,
            message: rawText.slice(0, 300) || `HTTP ${res.status} response`,
          },
        };
      }
    }

    if (!res.ok) {
      if (data && typeof data === "object" && !Array.isArray(data)) {
        if (!data.error && data.detail !== undefined) {
          if (typeof data.detail === "string") {
            data.error = { code: `HTTP_${res.status}`, message: data.detail };
          } else if (Array.isArray(data.detail)) {
            const msg = data.detail
              .map((e: any) => e?.msg || JSON.stringify(e))
              .join("; ");
            data.error = {
              code: "VALIDATION_ERROR",
              message: msg || "Validation error",
              details: data.detail,
            };
          } else if (typeof data.detail === "object") {
            data.error = {
              code: data.detail.code || `HTTP_${res.status}`,
              message: data.detail.message || JSON.stringify(data.detail),
              details: data.detail.details,
            };
          }
        }
        if (data.success === undefined) {
          data.success = false;
        }
      } else {
        data = {
          success: false,
          error: {
            code: `HTTP_${res.status}`,
            message: `Request failed with status ${res.status}`,
          },
        };
      }

      if (res.status === 401 || res.status === 403) {
        handleAuthOrTenantFailure(res.status, data?.error?.code);
      }
    }

    return data;
  } catch (err: any) {
    return {
      success: false,
      error: {
        code: "NETWORK_ERROR",
        message: err.message || "Failed to communicate with Talox API gateway",
      },
    };
  }
}
