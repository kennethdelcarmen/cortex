import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const foundations = [
  {
    label: "Focus",
    description: "Tasks and time blocks",
  },
  {
    label: "Memory",
    description: "Notes and reflections",
  },
  {
    label: "Money",
    description: "Cash flow and budgets",
  },
];

export default function Home() {
  return (
    <main className="flex min-h-[100svh] items-center justify-center px-6 py-16 sm:px-10">
      <div className="w-full max-w-4xl">
        <header className="max-w-2xl">
          <p className="font-mono text-xs font-medium uppercase tracking-[0.24em] text-primary">
            Cortex / local-first life manager
          </p>
          <h1 className="mt-6 max-w-2xl text-4xl font-semibold tracking-[-0.04em] text-foreground sm:text-6xl">
            A clear surface for the life you&apos;re carrying.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
            Tasks, notes, schedules, and money—kept close, calm, and under your
            control.
          </p>
        </header>

        <Card className="mt-12 max-w-2xl border-primary/20 bg-card/90 shadow-[0_24px_80px_-40px_color-mix(in_oklab,var(--primary)_35%,transparent)]">
          <CardHeader className="gap-4 border-b border-border/70">
            <div className="flex items-start justify-between gap-6">
              <div>
                <p className="font-mono text-[0.68rem] uppercase tracking-[0.18em] text-muted-foreground">
                  Workspace status
                </p>
                <CardTitle className="mt-3 text-xl tracking-[-0.02em] sm:text-2xl">
                  The foundation is ready.
                </CardTitle>
              </div>
              <span className="inline-flex shrink-0 items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1.5 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-primary">
                <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
                Local
              </span>
            </div>
            <CardDescription className="max-w-lg text-sm leading-6">
              The visual workspace is connected to the tools it will grow
              around. Your data stays close to the service you run.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 pt-5 sm:grid-cols-3">
            {foundations.map((foundation) => (
              <div
                key={foundation.label}
                className="border-l-2 border-primary/40 pl-3"
              >
                <p className="text-sm font-medium text-foreground">
                  {foundation.label}
                </p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {foundation.description}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>

        <p className="mt-8 font-mono text-[0.68rem] uppercase tracking-[0.16em] text-muted-foreground">
          Start with what deserves your attention today.
        </p>
      </div>
    </main>
  );
}
