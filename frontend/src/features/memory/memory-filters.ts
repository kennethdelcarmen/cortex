export type MemoryUrlState = {
  search: string;
  tag: string | undefined;
  noteId: string | undefined;
};

export function parseMemoryUrlState(params: URLSearchParams): MemoryUrlState {
  const search = params.get("q")?.trim().slice(0, 200) ?? "";
  const tag = params.get("tag")?.trim().toLowerCase() || undefined;
  const noteId = params.get("note")?.trim() || undefined;

  return { search, tag, noteId };
}

export function clearMemorySelection(params: URLSearchParams) {
  params.delete("note");
}
