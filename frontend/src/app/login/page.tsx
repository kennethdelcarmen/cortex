import { AuthLayout } from "@/features/auth/components/auth-layout";
import { AuthRouteGuard } from "@/features/auth/components/auth-route-guard";
import { LoginForm } from "@/features/auth/components/login-form";

export const metadata = {
  title: "Sign in · Cortex",
  description: "Sign in to your local Cortex workspace.",
};

export default function LoginPage() {
  return (
    <AuthRouteGuard>
      <AuthLayout
        title="Welcome back to your workspace."
        description="Sign in with the owner account for this local Cortex installation."
        footer={
          <>
            Cortex is local-first by default. Your session stays with the service you run.
          </>
        }
      >
        <LoginForm />
      </AuthLayout>
    </AuthRouteGuard>
  );
}
