import {
  WorkspaceModuleRoute,
} from "@/features/workspace/components/workspace-shell";

export const metadata = {
  title: "Money · Cortex",
  description: "The cash flow and budgets workspace for Cortex.",
};

export default function MoneyPage() {
  return <WorkspaceModuleRoute moduleKey="money" />;
}
