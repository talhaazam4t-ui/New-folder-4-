/**
 * Client-Side Authentication, Session Persistence & Tenant State Management
 * Enforces exclusive Sole Admin verification (SOLE_ADMIN_EMAILS + backend isSuperAdmin)
 * and long-lived session persistence for client accounts.
 */

export const SUPPORT_WHATSAPP_NUMBER = "03238300330";
export const SUPPORT_WHATSAPP_LINK = "https://wa.me/923238300330?text=Hi%20Teloxtech%2C%20I%20would%20like%20to%20inquire%20about%20your%20services";

export const SOLE_ADMIN_EMAILS: readonly string[] = [
  "talhazam4@gmail.com",
  "talhaazam4t@gmail.com",
  "talazam40@gmail.com",
];

export interface UserSession {
  userId: string;
  email: string;
  fullName: string;
  token: string;
  isSuperAdmin?: boolean;
  rememberMe?: boolean;
  savedAt?: number;
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
const PERSISTENCE_KEY = "talox_session_persistent";

export function isSoleAdminEmail(email?: string | null): boolean {
  if (!email) return false;
  const normalized = email.trim().toLowerCase();
  return SOLE_ADMIN_EMAILS.includes(normalized);
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string, persist = true): void {
  if (typeof window === "undefined") return;
  if (persist) {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(PERSISTENCE_KEY, "true");
  } else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(PERSISTENCE_KEY);
    sessionStorage.setItem(TOKEN_KEY, token);
  }
}

export function getCurrentUser(): UserSession | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setCurrentUser(user: UserSession, persist = true): void {
  if (typeof window === "undefined") return;
  const serialized = JSON.stringify({
    ...user,
    isSuperAdmin: Boolean(user.isSuperAdmin || isSoleAdminEmail(user.email)),
    savedAt: Date.now(),
  });
  if (persist) {
    sessionStorage.removeItem(USER_KEY);
    localStorage.setItem(USER_KEY, serialized);
    localStorage.setItem(PERSISTENCE_KEY, "true");
  } else {
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(PERSISTENCE_KEY);
    sessionStorage.setItem(USER_KEY, serialized);
  }
}

/**
 * Strict Super Admin check: True when backend verified super-admin or email matches SOLE_ADMIN_EMAILS.
 */
export function isSuperAdminUser(): boolean {
  const user = getCurrentUser();
  if (!user || !user.email) return false;
  return Boolean(user.isSuperAdmin || isSoleAdminEmail(user.email));
}

export function getActiveTenant(): ActiveTenant | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(TENANT_KEY) || sessionStorage.getItem(TENANT_KEY);
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

export function setActiveTenant(tenant: ActiveTenant, persist = true): void {
  if (typeof window === "undefined") return;
  const serialized = JSON.stringify(tenant);
  if (persist) {
    sessionStorage.removeItem(TENANT_KEY);
    localStorage.setItem(TENANT_KEY, serialized);
  } else {
    localStorage.removeItem(TENANT_KEY);
    sessionStorage.setItem(TENANT_KEY, serialized);
  }
}

export function hasPersistentSession(): boolean {
  const token = getAuthToken();
  const user = getCurrentUser();
  return Boolean(token && user);
}

export function clearActiveTenant(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TENANT_KEY);
    sessionStorage.removeItem(TENANT_KEY);
  }
}

export function clearSession(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TENANT_KEY);
    localStorage.removeItem(PERSISTENCE_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(TENANT_KEY);
  }
}
