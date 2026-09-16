import {
  WorkspaceModuleRoute,
} from "@/features/workspace/components/workspace-shell";

export const metadata = {
  title: "Memory · Cortex",
  description: "The notes and reflections workspace for Cortex.",
};

export default function MemoryPage() {
  return <WorkspaceModuleRoute moduleKey="memory" />;
}
