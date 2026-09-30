"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ArrowUpDown,
  CalendarDays,
  Check,
  Clock3,
  ListTodo,
  RefreshCw,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";
import { useFeedback } from "@/components/feedback";
import { FileAttachmentPicker } from "@/components/file-attachment-picker";
import { TagPicker } from "@/components/tag-picker";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import { useActivityLogger } from "@/features/activity/hooks";
import { createTag, getTags, tagsQueryKey, type Tag } from "@/features/tags/api";
import { createTask, taskQueryKey, taskSummaryQueryKey, updateTask } from "@/features/tasks/api";
import {
  formValuesToPayload,
  TaskCreateDialog,
  type TaskFormValues,
} from "@/features/tasks/components/task-create-dialog";
import { currentLocalDateInput } from "@/lib/date";
import { filesQueryKey } from "@/features/memory/files-api";
import { createNote, noteSummaryQueryKey, notesQueryKey, type NoteWriteInput } from "@/features/memory/api";
import { htmlToText } from "@/features/memory/components/html-content";
import { RichTextEditor } from "@/features/memory/components/rich-text-editor";
import { formatMoney, formatSignedMoney, currentPeriod, periodLabel } from "@/features/money/utils";
import { useMoneyCatalog } from "@/features/money/hooks";
import { TransactionDrawer } from "@/features/money/components/transaction-drawer";
import { CaptureMenu } from "@/features/workspace/components/capture-menu";
import { WorkspaceShell } from "@/features/workspace/components/workspace-shell";
import { invalidateHomeQueries, useHomeSummary } from "../hooks";
import type { HomeActivity, HomeSummary } from "../api";

type CaptureKey = "task" | "note" | "expense";

function greetingForHour(hour: number) {
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function formatHeaderDate(date: Date | null) {
  if (!date) return null;

  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function formatShortDate(value: string | null) {
  if (!value) return "Undated";
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  return Number.isNaN(date.valueOf())
    ? "Undated"
    : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function taskDueLabel(task: HomeSummary["tasks"]["items"][number]) {
  if (task.overdue) return "Overdue";
  if (!task.due_at) return "No due date";
  return `Due ${new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(task.due_at))}`;
}

function activityCopy(log: HomeActivity) {
  const title = log.metadata.title;
  const detail = typeof title === "string" && title.trim() ? title : null;

  switch (log.event_type) {
    case "task.created":
      return { summary: "Created task", detail };
    case "task.updated":
      return { summary: "Updated task", detail };
    case "task.deleted":
      return { summary: "Deleted task", detail };
    case "auth.logged_in":
      return { summary: "Signed in", detail: null };
    case "auth.setup_completed":
      return { summary: "Created the owner workspace", detail: null };
    case "auth.logged_out":
      return { summary: "Signed out", detail: null };
    default:
      return { summary: "Activity recorded", detail: log.event_type };
  }
}

function StatCard({
  label,
  value,
  detail,
  href,
  icon: Icon,
}: {
  label: string;
  value: string;
  detail: string;
  href: string;
  icon: typeof ListTodo;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <Card className="h-full border-border/80 transition-colors group-hover:border-primary/40 group-focus-visible:border-primary/50">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-3">
            <span className="font-mono text-[0.65rem] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              {label}
            </span>
            <Icon aria-hidden="true" className="size-4 text-primary-strong" />
          </div>
          <p className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-foreground">{value}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{detail}</p>
        </CardContent>
      </Card>
    </Link>
  );
}

function StatsSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-hidden="true">
      {Array.from({ length: 4 }).map((_, index) => (
        <Card key={index} className="border-border/80">
          <CardContent className="space-y-4 p-5">
            <Skeleton className="h-3 w-2/5" />
            <Skeleton className="h-8 w-1/3" />
            <Skeleton className="h-3 w-3/5" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  id,
  href,
  actionLabel,
}: {
  eyebrow: string;
  title: string;
  id: string;
  href?: string;
  actionLabel?: string;
}) {
  return (
    <div className="flex items-end justify-between gap-3">
      <div>
        <p className="font-mono text-[0.65rem] uppercase tracking-[0.18em] text-muted-foreground">{eyebrow}</p>
        <h2 id={id} className="mt-2 text-xl font-medium tracking-[-0.025em] text-foreground">{title}</h2>
      </div>
      {href ? (
        <Link
          href={href}
          className="rounded-md px-2 py-1 font-mono text-[0.64rem] uppercase tracking-[0.12em] text-primary-strong outline-none hover:bg-primary/8 focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {actionLabel ?? "View all"}
        </Link>
      ) : null}
    </div>
  );
}

function FocusSection({
  summary,
  onAdd,
  onComplete,
  completingId,
}: {
  summary: HomeSummary;
  onAdd: () => void;
  onComplete: (id: string) => void;
  completingId: string | null;
}) {
  const tasks = summary.tasks.items;

  return (
    <section aria-labelledby="home-focus-title">
      <SectionHeading id="home-focus-title" eyebrow="Focus" title="The next meaningful moves" href="/focus" actionLabel="Open focus" />
      <Card className="relative mt-4 overflow-hidden border-border/80 p-0">
        <span className="absolute inset-y-0 left-0 w-1 bg-primary/80" aria-hidden="true" />
        {tasks.length ? (
          <ul className="divide-y divide-border/70" aria-label="Tasks needing attention">
            {tasks.map((task) => (
              <li key={task.id} className="flex items-center gap-3 px-5 py-4 sm:px-6">
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  aria-label={`Mark ${task.title} complete`}
                  onClick={() => onComplete(task.id)}
                  disabled={completingId === task.id}
                  className="shrink-0 rounded-full border-border/90"
                >
                  {completingId === task.id ? <RefreshCw aria-hidden="true" className="animate-spin" /> : <Check aria-hidden="true" />}
                </Button>
                <div className="min-w-0 flex-1">
                  <Link href={`/focus?task=${encodeURIComponent(task.id)}`} className="block truncate text-sm font-medium text-foreground outline-none hover:text-primary-strong focus-visible:underline focus-visible:underline-offset-4">
                    {task.title}
                  </Link>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[0.63rem] uppercase tracking-[0.09em] text-muted-foreground">
                    <span className={task.overdue ? "text-destructive" : undefined}>{taskDueLabel(task)}</span>
                    {task.priority !== "none" ? <><span aria-hidden="true">·</span><span>{task.priority} priority</span></> : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="px-6 py-10 text-center sm:px-10">
            <ListTodo aria-hidden="true" className="mx-auto size-6 text-primary-strong" />
            <h3 className="mt-4 text-base font-medium">Your focus sequence is clear.</h3>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">Add a task when something deserves a place in today’s reach.</p>
            <Button type="button" size="sm" className="mt-5" onClick={onAdd}>Add task</Button>
          </div>
        )}
      </Card>
    </section>
  );
}

function MemorySection({ summary, onAdd }: { summary: HomeSummary; onAdd: () => void }) {
  return (
    <section aria-labelledby="home-memory-title">
      <SectionHeading id="home-memory-title" eyebrow="Memory" title="Recent notes" href="/memory" actionLabel="Open memory" />
      <Card className="mt-4 border-border/80">
        {summary.notes.items.length ? (
          <ul className="divide-y divide-border/70">
            {summary.notes.items.map((note) => (
              <li key={note.id}>
                <Link href={`/memory?note=${encodeURIComponent(note.id)}`} className="block px-5 py-4 outline-none hover:bg-muted/35 focus-visible:bg-muted/35 focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50 sm:px-6">
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="truncate text-sm font-medium">{note.title?.trim() || "Untitled entry"}</h3>
                    <span className="shrink-0 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-muted-foreground">{formatShortDate(note.journal_date)}</span>
                  </div>
                  <p className="mt-2 line-clamp-2 text-sm leading-5 text-muted-foreground">{note.preview || "No preview text yet."}</p>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <div className="px-6 py-10 text-center">
            <p className="text-sm font-medium">Your memory is still quiet.</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Capture a thought or reflection while it is still close.</p>
            <Button type="button" variant="outline" size="sm" className="mt-5" onClick={onAdd}>Add note</Button>
          </div>
        )}
      </Card>
    </section>
  );
}

function MoneySection({ summary, onAdd }: { summary: HomeSummary; onAdd: () => void }) {
  const budgetAmount = Number(summary.money.budget_amount);
  const spentAmount = Number(summary.money.budget_spent_amount);
  const budgetPercent = budgetAmount > 0 ? Math.min(100, Math.max(0, (spentAmount / budgetAmount) * 100)) : 0;

  return (
    <section aria-labelledby="home-money-title">
      <SectionHeading id="home-money-title" eyebrow="Money" title="Monthly pulse" href="/money" actionLabel="Open money" />
      <Card className="mt-4 border-border/80">
        <CardHeader className="p-5 pb-0 sm:p-6 sm:pb-0">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-lg">{periodLabel(summary.period)}</CardTitle>
              <CardDescription className="mt-1">Default view in {summary.currency_code}</CardDescription>
            </div>
            <WalletCards aria-hidden="true" className="size-5 text-primary-strong" />
          </div>
          <div className="mt-5 flex items-end justify-between gap-3">
            <div>
              <p className="font-mono text-[0.63rem] uppercase tracking-[0.12em] text-muted-foreground">Spent this month</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.035em]">{formatMoney(summary.money.spending_amount, summary.currency_code)}</p>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={onAdd}>Add expense</Button>
          </div>
        </CardHeader>
        <CardContent className="p-5 sm:p-6">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-muted-foreground">{budgetAmount > 0 ? `${formatMoney(summary.money.budget_spent_amount, summary.currency_code)} of ${formatMoney(summary.money.budget_amount, summary.currency_code)} budget` : "No monthly budget planned"}</span>
            {budgetAmount > 0 ? <span className="font-mono text-[0.65rem] uppercase tracking-[0.1em] text-primary-strong">{Math.round(budgetPercent)}%</span> : null}
          </div>
          {budgetAmount > 0 ? (
            <div
              className="mt-2 h-2 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label={`${Math.round(budgetPercent)} percent of monthly budget spent`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(budgetPercent)}
            >
              <div className="h-full rounded-full bg-primary transition-[width] duration-300 motion-reduce:transition-none" style={{ width: `${budgetPercent}%` }} />
            </div>
          ) : null}
          {summary.money.movements.length ? (
            <div className="mt-6 border-t border-border/70 pt-4">
              <p className="font-mono text-[0.63rem] uppercase tracking-[0.12em] text-muted-foreground">Recent movement</p>
              <ul className="mt-3 space-y-3">
                {summary.money.movements.map((movement) => {
                  const Icon = movement.direction === "income" ? ArrowDownLeft : movement.direction === "expense" ? ArrowUpRight : ArrowUpDown;
                  const signedAmount = movement.direction === "expense" ? `-${movement.amount}` : movement.direction === "income" ? movement.amount : "0";
                  return (
                    <li key={movement.id} className="flex items-center gap-3">
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground"><Icon aria-hidden="true" className="size-3.5" /></span>
                      <span className="min-w-0 flex-1 truncate text-sm">{movement.name}</span>
                      <span className={cn("shrink-0 font-mono text-xs", movement.direction === "expense" ? "text-foreground" : "text-primary-strong")}>{movement.direction === "transfer" ? formatMoney(movement.amount, movement.currency_code) : formatSignedMoney(signedAmount, movement.currency_code)}</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : (
            <p className="mt-5 border-t border-border/70 pt-4 text-sm text-muted-foreground">No movements recorded for this month.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function ActivitySection({ activity }: { activity: HomeActivity[] }) {
  return (
    <section aria-labelledby="home-activity-title">
      <SectionHeading id="home-activity-title" eyebrow="History" title="Recent activity" />
      <Card className="mt-4 border-border/80">
        {activity.length ? (
          <ol className="divide-y divide-border/70 px-5 sm:px-6" aria-label="Recent activity">
            {activity.map((log) => {
              const copy = activityCopy(log);
              const createdAt = new Date(log.created_at);
              return (
                <li key={log.id} className="flex gap-3 py-4 first:pt-5 last:pb-5">
                  <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <p className="min-w-0 text-sm font-medium">{copy.summary}</p>
                      <time dateTime={log.created_at} className="shrink-0 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-muted-foreground">
                        {Number.isNaN(createdAt.valueOf()) ? "Recently" : formatDistanceToNow(createdAt, { addSuffix: true })}
                      </time>
                    </div>
                    {copy.detail ? <p className="mt-1 truncate text-xs text-muted-foreground">{copy.detail}</p> : null}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="px-6 py-8 text-center text-sm text-muted-foreground">Completed actions will stay close here.</div>
        )}
      </Card>
    </section>
  );
}

function HomeNoteCaptureDialog({
  open,
  availableTags,
  isSaving,
  onCreateTag,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  availableTags: Tag[];
  isSaving: boolean;
  onCreateTag: (payload: { name: string; color: import("@/features/tags/api").TagColor }) => Promise<Tag>;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: NoteWriteInput) => void;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("<p></p>");
  const [journalDate, setJournalDate] = useState(currentLocalDateInput());
  const [tags, setTags] = useState<string[]>([]);
  const [attachments, setAttachments] = useState<import("@/features/memory/files-api").StoredFile[]>([]);
  const [error, setError] = useState<string>();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!htmlToText(body).trim()) {
      setError("Add a little text before saving this note.");
      return;
    }
    onSubmit({
      title: title.trim() || null,
      body,
      journal_date: journalDate || null,
      tags,
      file_ids: attachments.map((file) => file.id),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(90svh,48rem)] w-[min(42rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border-border bg-card p-0 text-card-foreground sm:max-w-none">
        <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
          <DialogHeader className="border-b border-border/70 px-6 py-6 sm:px-7">
            <DialogTitle className="text-xl font-semibold tracking-[-0.03em]">Add note</DialogTitle>
            <DialogDescription className="mt-2 max-w-md text-sm leading-6">Keep a thought, reflection, or observation close to the rest of your day.</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-6 sm:px-7">
            {error ? <p className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive" role="alert">{error}</p> : null}
            <div className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_11rem]">
              <div>
                <Label htmlFor="home-note-title">Title</Label>
                <Input id="home-note-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Give this entry a clear title" maxLength={200} className="mt-2 min-h-11 bg-background" disabled={isSaving} />
              </div>
              <div>
                <Label htmlFor="home-note-date">Journal date</Label>
                <Input id="home-note-date" type="date" value={journalDate} onChange={(event) => setJournalDate(event.target.value)} className="mt-2 min-h-11 bg-background" disabled={isSaving} />
              </div>
            </div>
            <div>
              <Label htmlFor="home-note-tags">Tags</Label>
              <div className="mt-2"><TagPicker id="home-note-tags" tags={availableTags} value={tags} onChange={setTags} onCreateTag={onCreateTag} disabled={isSaving} /></div>
            </div>
            <FileAttachmentPicker id="home-note-attachments" value={attachments} onChange={setAttachments} disabled={isSaving} />
            <div>
              <Label>Body</Label>
              <div className="memory-editor mt-2 min-h-44 overflow-hidden rounded-lg border border-border/80 bg-background px-4 py-3">
                <RichTextEditor key={open ? "open" : "closed"} initialHtml={body} readOnly={false} onHtmlChange={setBody} />
              </div>
            </div>
          </div>
          <DialogFooter className="mx-0! mb-0! border-t border-border/70 bg-card px-6 py-4 sm:px-7">
            <Button type="button" variant="outline" size="lg" onClick={() => onOpenChange(false)} disabled={isSaving}>Cancel</Button>
            <Button type="submit" size="lg" disabled={isSaving}>{isSaving ? "Saving…" : "Save note"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function HomeDashboard({
  summaryQuery,
  displayName,
  onAdd,
  onComplete,
  completingId,
}: {
  summaryQuery: ReturnType<typeof useHomeSummary>;
  displayName: string | null;
  onAdd: (key: CaptureKey) => void;
  onComplete: (id: string) => void;
  completingId: string | null;
}) {
  const summary = summaryQuery.data;
  const errorDescription = summaryQuery.error instanceof ApiError ? summaryQuery.error.message : "The Home summary could not be loaded.";
  const now = new Date();
  const greetingName = displayName?.trim() || "there";

  return (
    <div>
      <header className="flex flex-col gap-5 border-b border-border/70 pb-7 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
        <div className="max-w-2xl">
          <p suppressHydrationWarning className="font-mono text-[0.66rem] uppercase tracking-[0.18em] text-primary-strong">{formatHeaderDate(now) ?? "Today"}</p>
          <h1 suppressHydrationWarning className="mt-3 text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">{greetingForHour(now.getHours())}, {greetingName}.</h1>
          <p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">A clear place to see what needs attention, what is staying close, and how the month is moving.</p>
        </div>
        <div className="shrink-0 self-start sm:self-auto"><CaptureMenu onSelect={onAdd} /></div>
      </header>

      <div className="mt-7 sm:mt-8">
        {summaryQuery.isPending ? <StatsSkeleton /> : summaryQuery.isError || !summary ? <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><Card className="sm:col-span-2 xl:col-span-4 border-destructive/30 bg-destructive/5"><CardContent className="p-5"><p className="text-sm font-medium">Home is unavailable right now.</p><p className="mt-1 text-sm text-muted-foreground">{errorDescription}</p><Button type="button" variant="outline" size="sm" className="mt-4" onClick={() => void summaryQuery.refetch()} disabled={summaryQuery.isFetching}><RefreshCw aria-hidden="true" className={cn(summaryQuery.isFetching && "animate-spin")} />{summaryQuery.isFetching ? "Retrying…" : "Try again"}</Button></CardContent></Card></div> : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Today’s tasks" value={String(summary.tasks.counts.today)} detail={`${summary.tasks.counts.overdue} overdue`} href="/focus?view=today" icon={ListTodo} />
            <StatCard label="Upcoming" value={String(summary.tasks.counts.upcoming)} detail="Active tasks ahead" href="/focus?view=upcoming" icon={CalendarDays} />
            <StatCard label="Active notes" value={String(summary.notes.count)} detail="Journal and notes" href="/memory" icon={Clock3} />
            <StatCard label="This month" value={formatMoney(summary.money.spending_amount, summary.currency_code)} detail={periodLabel(summary.period)} href="/money" icon={WalletCards} />
          </div>
        )}
      </div>

      {summaryQuery.isError || !summary ? null : (
        <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)] lg:gap-12">
          <div className="space-y-10">
            <FocusSection summary={summary} onAdd={() => onAdd("task")} onComplete={onComplete} completingId={completingId} />
            <MoneySection summary={summary} onAdd={() => onAdd("expense")} />
          </div>
          <div className="space-y-10">
            <MemorySection summary={summary} onAdd={() => onAdd("note")} />
            <ActivitySection activity={summary.activity} />
          </div>
        </div>
      )}
    </div>
  );
}

export default function HomePage({ email, displayName }: { email: string; displayName: string | null }) {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const logActivity = useActivityLogger();
  const [timezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [captureMode, setCaptureMode] = useState<CaptureKey | null>(null);
  const [completingId, setCompletingId] = useState<string | null>(null);
  const period = currentPeriod();
  const homeQuery = useHomeSummary(timezone, period, "PHP");
  const tagsQuery = useQuery({ queryKey: tagsQueryKey, queryFn: () => getTags(true) });
  const moneyCatalog = useMoneyCatalog();
  const availableTags = useMemo(() => tagsQuery.data?.items ?? [], [tagsQuery.data?.items]);

  const createTagMutation = useMutation({
    mutationFn: createTag,
    onSuccess: (tag) => {
      queryClient.setQueryData<{ items: Tag[] }>(tagsQueryKey, (current) => ({
        items: [...(current?.items ?? []).filter((item) => item.id !== tag.id), tag],
      }));
    },
  });
  const createTaskMutation = useMutation({
    mutationFn: createTask,
    onSuccess: async (task) => {
      await invalidateHomeQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      void queryClient.invalidateQueries({ queryKey: filesQueryKey });
      void logActivity({ event_type: "task.created", entity_type: "task", entity_id: task.id, metadata: { title: task.title } });
      setCaptureMode(null);
      feedback.success({ title: "Task added." });
    },
    onError: (error) => feedback.error({ title: "Task could not be added.", description: error instanceof ApiError ? error.message : "Try again." }),
  });
  const createNoteMutation = useMutation({
    mutationFn: createNote,
    onSuccess: async () => {
      await invalidateHomeQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: notesQueryKey });
      void queryClient.invalidateQueries({ queryKey: noteSummaryQueryKey });
      void queryClient.invalidateQueries({ queryKey: filesQueryKey });
      setCaptureMode(null);
      feedback.success({ title: "Note saved." });
    },
    onError: (error) => feedback.error({ title: "Note could not be saved.", description: error instanceof ApiError ? error.message : "Try again." }),
  });
  const completeMutation = useMutation({
    mutationFn: (taskId: string) => updateTask(taskId, { status: "done" }),
    onMutate: (taskId) => setCompletingId(taskId),
    onSuccess: async (task) => {
      await invalidateHomeQueries(queryClient);
      void queryClient.invalidateQueries({ queryKey: taskQueryKey });
      void queryClient.invalidateQueries({ queryKey: taskSummaryQueryKey });
      void logActivity({ event_type: "task.updated", entity_type: "task", entity_id: task.id, metadata: { title: task.title, status: task.status } });
      feedback.success({ title: "Task completed." });
    },
    onError: (error) => feedback.error({ title: "Task could not be completed.", description: error instanceof ApiError ? error.message : "Try again." }),
    onSettled: () => setCompletingId(null),
  });

  return (
    <WorkspaceShell email={email} onCapture={setCaptureMode}>
      <HomeDashboard summaryQuery={homeQuery} displayName={displayName} onAdd={setCaptureMode} onComplete={(id) => completeMutation.mutate(id)} completingId={completingId} />
      <TaskCreateDialog
        key={captureMode === "task" ? "task-open" : "task-closed"}
        open={captureMode === "task"}
        isSaving={createTaskMutation.isPending}
        availableTags={availableTags}
        onCreateTag={(payload) => createTagMutation.mutateAsync(payload)}
        onOpenChange={(open) => { if (!open) setCaptureMode(null); }}
        onSubmit={(values: TaskFormValues) => createTaskMutation.mutate(formValuesToPayload(values))}
      />
      <HomeNoteCaptureDialog
        key={captureMode === "note" ? "note-open" : "note-closed"}
        open={captureMode === "note"}
        availableTags={availableTags}
        isSaving={createNoteMutation.isPending}
        onCreateTag={(payload) => createTagMutation.mutateAsync(payload)}
        onOpenChange={(open) => { if (!open) setCaptureMode(null); }}
        onSubmit={(payload) => createNoteMutation.mutate(payload)}
      />
      <TransactionDrawer
        open={captureMode === "expense"}
        onOpenChange={(open) => { if (!open) setCaptureMode(null); }}
        onSaved={() => { void invalidateHomeQueries(queryClient); setCaptureMode(null); }}
        accounts={moneyCatalog.accounts}
        payees={moneyCatalog.payees}
        categories={moneyCatalog.categories}
        defaultDate={currentLocalDateInput()}
        defaultCurrencyCode="PHP"
      />
    </WorkspaceShell>
  );
}
