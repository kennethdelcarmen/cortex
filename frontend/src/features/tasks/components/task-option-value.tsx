import { cn } from "@/lib/utils";
import type { TaskPriorityOption, TaskStatusOption } from "../utils";

type TaskOption = TaskPriorityOption | TaskStatusOption;

export function TaskOptionValue({
  option,
  className,
}: {
  option: TaskOption;
  className?: string;
}) {
  const Icon = option.icon;

  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)}>
      <Icon aria-hidden="true" className={cn("size-4 shrink-0", option.colorClass)} />
      <span className="truncate">{option.label}</span>
    </span>
  );
}
