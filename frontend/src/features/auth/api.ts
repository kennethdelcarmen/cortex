import { z } from "zod";
import { ApiError, apiFetch } from "@/lib/api/client";

const userResponseSchema = z.object({
  id: z.string().min(1),
  email: z.string().email(),
  created_at: z.string().min(1),
});

const mcpApiKeyResponseSchema = z.object({
  configured: z.boolean(),
  revoked: z.boolean(),
  created_at: z.string().nullable(),
  updated_at: z.string().nullable(),
  revoked_at: z.string().nullable(),
});

export type User = z.infer<typeof userResponseSchema>;

export const authQueryKey = ["auth", "me"] as const;

export async function getCurrentUser(): Promise<User | null> {
  try {
    return await apiFetch("/api/v1/auth/me", {}, userResponseSchema);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }

    throw error;
  }
}

export async function setupOwner(input: {
  email: string;
  password: string;
  setupSecret: string;
  mcpApiKey?: string;
  useSetupSecretAsMcpKey: boolean;
}): Promise<User> {
  return apiFetch(
    "/api/v1/auth/setup",
    {
      method: "POST",
      headers: {
        "X-Setup-Secret": input.setupSecret,
      },
      body: JSON.stringify({
        email: input.email.trim(),
        password: input.password,
        mcp_api_key: input.mcpApiKey,
        use_setup_secret_as_mcp_key: input.useSetupSecretAsMcpKey,
      }),
    },
    userResponseSchema,
  );
}

export type McpApiKeyStatus = z.infer<typeof mcpApiKeyResponseSchema>;

export async function getMcpApiKeyStatus(): Promise<McpApiKeyStatus> {
  return apiFetch("/api/v1/auth/mcp-key", {}, mcpApiKeyResponseSchema);
}

export async function replaceMcpApiKey(key: string): Promise<McpApiKeyStatus> {
  return apiFetch(
    "/api/v1/auth/mcp-key",
    {
      method: "PUT",
      body: JSON.stringify({ key }),
    },
    mcpApiKeyResponseSchema,
  );
}

export async function revokeMcpApiKey(): Promise<void> {
  await apiFetch<void>("/api/v1/auth/mcp-key", { method: "DELETE" });
}

export async function verifySetupSecret(setupSecret: string): Promise<void> {
  await apiFetch<void>("/api/v1/auth/setup/verify", {
    method: "POST",
    headers: {
      "X-Setup-Secret": setupSecret,
    },
  });
}

export async function login(input: {
  email: string;
  password: string;
}): Promise<User> {
  return apiFetch(
    "/api/v1/auth/login",
    {
      method: "POST",
      body: JSON.stringify({
        email: input.email.trim(),
        password: input.password,
      }),
    },
    userResponseSchema,
  );
}

export async function logout(): Promise<void> {
  await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
}

export function describeAuthError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The request could not be completed. Try again.";
  }

  switch (error.code) {
    case "network_error":
      return "Cortex could not be reached. Check that the backend is running and try again.";
    case "invalid_setup_secret":
      return "That setup secret did not match this installation.";
    case "auth_already_initialized":
      return "This installation already has an owner. Sign in instead.";
    case "setup_not_configured":
      return "Owner setup is not available yet. Set CORTEX_SETUP_SECRET before trying again.";
    case "invalid_mcp_api_key_configuration":
      return "Use a separate MCP key with at least 32 characters, or choose the setup secret option.";
    case "invalid_credentials":
      return "That email or password did not match. Try again.";
    case "invalid_response":
      return "The Cortex service returned an unexpected response. Try again.";
    default:
      return "The request could not be completed. Try again.";
  }
}
