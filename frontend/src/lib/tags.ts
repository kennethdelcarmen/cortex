export type TagUsage = {
  name: string;
  count: number;
};

export function mostUsedTagNames(tags: TagUsage[], limit = 6) {
  return [...tags]
    .sort(
      (left, right) =>
        right.count - left.count || left.name.localeCompare(right.name),
    )
    .slice(0, limit)
    .map((tag) => tag.name);
}
