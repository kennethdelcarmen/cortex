import { MemoryFilesRoute } from "@/features/memory/components/files-page";

export const metadata = {
  title: "Files · Memory · Cortex",
  description: "The local file library for Cortex memory.",
};

export default function MemoryFilesRoutePage() {
  return <MemoryFilesRoute />;
}
