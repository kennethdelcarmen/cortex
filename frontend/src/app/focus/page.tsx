import { TasksRoute } from "@/features/tasks/components/tasks-page";

export const metadata = {
  title: "Focus · Cortex",
  description: "The task and time-block workspace for Cortex.",
};

export default function FocusPage() {
  return <TasksRoute />;
}
