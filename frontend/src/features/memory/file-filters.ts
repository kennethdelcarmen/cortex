import type { FileContextStatus } from "./files-api";

export const FILE_CONTEXT_STATUSES = [
  "pending",
  "processing",
  "ready",
  "unsupported",
  "failed",
] as const satisfies readonly FileContextStatus[];

export type FileUrlState = {
  search: string;
  tags: string[];
  contextStatuses: FileContextStatus[];
};

const statusSet = new Set<string>(FILE_CONTEXT_STATUSES);

export function parseFileUrlState(params: URLSearchParams): FileUrlState {
  const tags = Array.from(
    new Set(
      params
        .getAll("tag")
        .map((value) => value.trim().toLowerCase())
        .filter(Boolean),
    ),
  ).slice(0, 20);
  const contextStatuses = Array.from(
    new Set(
      params
        .getAll("context_status")
        .filter((value): value is FileContextStatus => statusSet.has(value)),
    ),
  );

  return {
    search: params.get("q")?.trim().slice(0, 200) ?? "",
    tags,
    contextStatuses,
  };
}

export function clearFileUrlState(params: URLSearchParams) {
  params.delete("q");
  params.delete("tag");
  params.delete("context_status");
}
