import type { LucideIcon } from "lucide-react";
import { BookOpen, Home, ListTodo, Settings2, Trash2, WalletCards } from "lucide-react";

export type WorkspaceModule = "focus" | "memory" | "money";
export type WorkspaceSection = "home" | WorkspaceModule | "trash" | "settings";

export type WorkspaceNavigationItem = {
  key: WorkspaceSection;
  label: string;
  href: string;
  description: string;
  icon: LucideIcon;
};

export type WorkspaceModuleDefinition = {
  key: WorkspaceModule;
  label: string;
  href: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
  icon: LucideIcon;
};

export const moduleDefinitions: Record<WorkspaceModule, WorkspaceModuleDefinition> = {
  focus: {
    key: "focus",
    label: "Focus",
    href: "/focus",
    description: "Tasks and time blocks",
    emptyTitle: "Your focus sequence is ready for its first move.",
    emptyDescription:
      "This is where the small set of tasks and time blocks that deserve your attention will come together.",
    icon: ListTodo,
  },
  memory: {
    key: "memory",
    label: "Memory",
    href: "/memory",
    description: "Notes and reflections",
    emptyTitle: "Your memory is still quiet.",
    emptyDescription:
      "Notes, journals, and reflections will have a place to stay close and useful here.",
    icon: BookOpen,
  },
  money: {
    key: "money",
    label: "Money",
    href: "/money",
    description: "Cash flow and budgets",
    emptyTitle: "Your money workspace is not connected yet.",
    emptyDescription:
      "Balances, spending, and monthly budgets will be kept together here when the financial engine is ready.",
    icon: WalletCards,
  },
};

export const workspaceNavigation: WorkspaceNavigationItem[] = [
  {
    key: "home",
    label: "Home",
    href: "/",
    description: "Your day in reach",
    icon: Home,
  },
  ...Object.values(moduleDefinitions),
  {
    key: "trash",
    label: "Trash",
    href: "/trash",
    description: "Deleted and archived records",
    icon: Trash2,
  },
  {
    key: "settings",
    label: "Settings",
    href: "/settings",
    description: "Account and agent access",
    icon: Settings2,
  },
];

export const captureOptions = [
  {
    key: "task",
    label: "Task",
    description: "A next action or time block",
    icon: ListTodo,
  },
  {
    key: "note",
    label: "Note",
    description: "A thought, journal, or reflection",
    icon: BookOpen,
  },
  {
    key: "expense",
    label: "Expense",
    description: "A transaction or budget item",
    icon: WalletCards,
  },
] as const;
