/**
 * Client-Side Authentication & Active Tenant State Management
 * Note: Only non-sensitive session metadata and JWT access token are stored here.
 * Third-party integration credentials, API keys, and refresh tokens are NEVER stored in localStorage.
 */

export interface UserSession {
  userId: string;
  email: string;
  fullName: string;
  token: string;
  isSuperAdmin?: boolean;
}

export interface ActiveTenant {
  id: string;
  name: string;
  slug: string;
  industry?: string;
  status?: string;
  role?: string;
  settings?: Record<string, any>;
}

const TOKEN_KEY = "talox_token";
const USER_KEY = "talox_user";
const TENANT_KEY = "talox_active_tenant";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

export function getCurrentUser(): UserSession | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setCurrentUser(user: UserSession): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
}

export function isSuperAdminUser(): boolean {
  const user = getCurrentUser();
  if (!user) return false;
  if (typeof user.isSuperAdmin === "boolean") return user.isSuperAdmin;
  const email = (user.email || "").toLowerCase();
  return email.endsWith("@talox.com") || email.endsWith("@talox.io");
}

export function getActiveTenant(): ActiveTenant | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(TENANT_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed === "string") {
      return { id: parsed, name: "Workspace", slug: "workspace" };
    }
    return parsed;
  } catch {
    return null;
  }
}

export function getActiveTenantId(): string | null {
  const tenant = getActiveTenant();
  return tenant?.id || null;
}

export function setActiveTenant(tenant: ActiveTenant): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(TENANT_KEY, JSON.stringify(tenant));
  }
}

export function clearSession(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TENANT_KEY);
  }
}
