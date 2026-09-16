import {
  WorkspaceModuleRoute,
} from "@/features/workspace/components/workspace-shell";

export const metadata = {
  title: "Focus · Cortex",
  description: "The task and time-block workspace for Cortex.",
};

export default function FocusPage() {
  return <WorkspaceModuleRoute moduleKey="focus" />;
}
