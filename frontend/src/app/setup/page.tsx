import { AuthLayout } from "@/features/auth/components/auth-layout";
import { AuthRouteGuard } from "@/features/auth/components/auth-route-guard";
import { SetupWizard } from "@/features/auth/components/setup-wizard";

export const metadata = {
  title: "Set up Cortex",
  description: "Initialize the owner account for a local Cortex installation.",
};

export default function SetupPage() {
  return (
    <AuthRouteGuard>
      <AuthLayout
        title="Make this installation yours."
        description="Connect the service, create the first owner account, and keep your workspace close to home."
      >
        <SetupWizard />
      </AuthLayout>
    </AuthRouteGuard>
  );
}
