/**
 * Cliente HTTP. Toda escritura lleva el header X-CSRF-Token con el valor de la cookie `ccap_csrf`
 * (double-submit cookie, ver app/csrf.py). Las credenciales viajan por cookie/cabeceras del proxy de
 * Databricks: el frontend nunca guarda ni ve tokens.
 */
export class ApiError extends Error {
  status: number;
  errors: { bloque: number | string; error: string }[];

  constructor(status: number, message: string, errors: { bloque: number | string; error: string }[] = []) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

export function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[1]) : null;
}

async function errorFrom(resp: Response): Promise<ApiError> {
  try {
    const data = await resp.json();
    const detail = data?.detail;
    if (typeof detail === "string") return new ApiError(resp.status, detail);
    if (Array.isArray(detail)) {
      // Validación de FastAPI/Pydantic: [{loc, msg, ...}]
      return new ApiError(resp.status, detail.map((d: { msg?: string }) => d.msg ?? "dato inválido").join("; "));
    }
    if (detail && typeof detail === "object") {
      const errors = Array.isArray(detail.errors) ? detail.errors : [];
      return new ApiError(resp.status, detail.message ?? `Error HTTP ${resp.status}`, errors);
    }
  } catch {
    /* cuerpo no JSON */
  }
  return new ApiError(resp.status, `Error HTTP ${resp.status}`);
}

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);

export async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (!SAFE.has(method)) {
    const token = getCookie("ccap_csrf");
    if (token) headers.set("X-CSRF-Token", token);
  }
  const resp = await fetch(url, { ...init, headers, credentials: "same-origin" });
  if (!resp.ok) throw await errorFrom(resp);
  return resp;
}

export async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await apiFetch(url, init);
  return resp.status === 204 ? (undefined as T) : ((await resp.json()) as T);
}

export function apiJson<T>(url: string, method: string, body: unknown): Promise<T> {
  return api<T>(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

/** POST multipart con avance del envío (`fetch` no lo informa). `onProgress` recibe 0–1. */
export function uploadWithProgress<T>(url: string, body: FormData, onProgress: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.withCredentials = true;
    const token = getCookie("ccap_csrf");
    if (token) xhr.setRequestHeader("X-CSRF-Token", token);
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) onProgress(ev.loaded / ev.total);
    };
    xhr.onload = async () => {
      const resp = new Response(xhr.responseText, { status: xhr.status, headers: { "Content-Type": "application/json" } });
      if (resp.ok) resolve((await resp.json()) as T);
      else reject(await errorFrom(resp));
    };
    xhr.onerror = () => reject(new ApiError(0, "No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo."));
    xhr.send(body);
  });
}

export async function download(url: string, filename: string): Promise<void> {
  const resp = await apiFetch(url);
  const blob = await resp.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Error inesperado";
}
