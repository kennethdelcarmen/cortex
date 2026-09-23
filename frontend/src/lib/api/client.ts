import { z } from "zod";

const apiBaseUrl = z
  .string()
  .url()
  .parse(process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000");

const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

const apiErrorResponseSchema = z.object({
  detail: z
    .union([
      z.object({
        code: z.string(),
        message: z.string(),
        unknown_tags: z.array(z.string()).optional(),
        allowed_tags: z.array(z.string()).optional(),
      }),
      z.string(),
    ])
    .optional(),
  code: z.string().optional(),
  message: z.string().optional(),
});

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly unknownTags?: string[];
  readonly allowedTags?: string[];

  constructor(
    status: number,
    code: string,
    message: string,
    details?: { unknownTags?: string[]; allowedTags?: string[] },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.unknownTags = details?.unknownTags;
    this.allowedTags = details?.allowedTags;
  }
}

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") {
    return undefined;
  }

  const prefix = name + "=";
  const cookie = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(prefix));

  if (!cookie) {
    return undefined;
  }

  try {
    return decodeURIComponent(cookie.slice(prefix.length));
  } catch {
    return undefined;
  }
}

function parseApiError(status: number, body: unknown): ApiError {
  const parsed = apiErrorResponseSchema.safeParse(body);

  if (!parsed.success) {
    return new ApiError(status, "api_error", "The Cortex request failed.");
  }

  const detail = parsed.data.detail;

  if (detail && typeof detail === "object") {
    return new ApiError(status, detail.code, detail.message, {
      unknownTags: detail.unknown_tags,
      allowedTags: detail.allowed_tags,
    });
  }

  if (typeof detail === "string") {
    return new ApiError(status, "api_error", detail);
  }

  return new ApiError(
    status,
    parsed.data.code ?? "api_error",
    parsed.data.message ?? "The Cortex request failed.",
  );
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  schema?: z.ZodType<T>,
): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  const hasFormDataBody =
    typeof FormData !== "undefined" && init.body instanceof FormData;

  if (init.body && !hasFormDataBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (unsafeMethods.has(method) && !headers.has("X-CSRF-Token")) {
    const csrfToken = readCookie("cortex_csrf");

    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  let response: Response;

  try {
    response = await fetch(new URL(path, apiBaseUrl), {
      ...init,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(
      0,
      "network_error",
      "The Cortex service could not be reached.",
    );
  }

  if (!response.ok) {
    let body: unknown;

    try {
      body = await response.json();
    } catch {
      body = undefined;
    }

    throw parseApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  try {
    const payload: unknown = await response.json();
    return schema ? schema.parse(payload) : (payload as T);
  } catch {
    throw new ApiError(
      response.status,
      "invalid_response",
      "The Cortex service returned an unexpected response.",
    );
  }
}
