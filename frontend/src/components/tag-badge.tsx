import { cn } from "@/lib/utils";
import type { TagColor } from "@/features/tags/api";

const colorClasses: Record<TagColor, string> = {
  rose: "border-tag-rose/45 bg-tag-rose/15 text-tag-rose-foreground",
  "sea-glass": "border-tag-sea-glass/45 bg-tag-sea-glass/15 text-tag-sea-glass-foreground",
  amber: "border-tag-amber/45 bg-tag-amber/15 text-tag-amber-foreground",
  slate: "border-tag-slate/45 bg-tag-slate/15 text-tag-slate-foreground",
  plum: "border-tag-plum/45 bg-tag-plum/15 text-tag-plum-foreground",
  violet: "border-tag-violet/45 bg-tag-violet/15 text-tag-violet-foreground",
  sand: "border-tag-sand/45 bg-tag-sand/15 text-tag-sand-foreground",
  destructive: "border-tag-destructive/45 bg-tag-destructive/15 text-tag-destructive-foreground",
};

const swatchClasses: Record<TagColor, string> = {
  rose: "bg-tag-rose",
  "sea-glass": "bg-tag-sea-glass",
  amber: "bg-tag-amber",
  slate: "bg-tag-slate",
  plum: "bg-tag-plum",
  violet: "bg-tag-violet",
  sand: "bg-tag-sand",
  destructive: "bg-tag-destructive",
};

export function tagColorClass(color: TagColor | undefined) {
  return colorClasses[color ?? "slate"];
}

export function tagColorSwatchClass(color: TagColor) {
  return swatchClasses[color];
}

export function TagBadge({
  name,
  color,
  active = true,
  className,
}: {
  name: string;
  color?: TagColor;
  active?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-1 font-mono text-[0.68rem] font-medium",
        tagColorClass(color),
        !active && "border-dashed opacity-65",
        className,
      )}
    >
      <span aria-hidden="true">#</span>
      <span>{name}</span>
      {!active ? <span className="font-sans text-[0.6rem] font-normal">archived</span> : null}
    </span>
  );
}
