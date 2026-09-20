"use client";

import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import interactionPlugin from "@fullcalendar/interaction";
import timeGridPlugin from "@fullcalendar/timegrid";
import type {
  DatesSetArg,
  EventClickArg,
  EventContentArg,
  EventInput,
} from "@fullcalendar/core";
import type { DateClickArg } from "@fullcalendar/interaction";
import { CalendarDays, Clock3 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import type { Task } from "../api";
import { formatDateTime, priorityOption, statusLabel, statusOption } from "../utils";

export type TaskCalendarRange = {
  start: Date;
  end: Date;
};

export type TaskCalendarCreateSelection = {
  date: Date;
  allDay: boolean;
};

export function initialTaskCalendarRange(date = new Date()): TaskCalendarRange {
  return {
    start: new Date(date.getFullYear(), date.getMonth(), 1),
    end: new Date(date.getFullYear(), date.getMonth() + 1, 1),
  };
}

type TaskCalendarProps = {
  tasks: Task[];
  isPending: boolean;
  isFetching: boolean;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onFetchNextPage: () => void;
  onRangeChange: (range: TaskCalendarRange) => void;
  onOpenTask: (task: Task) => void;
  onCreateTask: (selection: TaskCalendarCreateSelection) => void;
};

function isMidnight(value: Date) {
  return value.getHours() === 0 &&
    value.getMinutes() === 0 &&
    value.getSeconds() === 0 &&
    value.getMilliseconds() === 0;
}

function eventForTask(task: Task): EventInput | null {
  const startValue = task.start_at ?? task.due_at;
  const endValue = task.due_at ?? task.start_at;

  if (!startValue) {
    return null;
  }

  const start = new Date(startValue);
  const end = endValue ? new Date(endValue) : null;

  if (Number.isNaN(start.getTime()) || (end && Number.isNaN(end.getTime()))) {
    return null;
  }

  const allDay = isMidnight(start) && (!end || isMidnight(end));
  const hasDistinctEnd = Boolean(end && end.getTime() > start.getTime());

  return {
    id: task.id,
    title: task.title,
    start,
    ...(hasDistinctEnd && end ? { end } : {}),
    allDay,
    classNames: [`cortex-task-event--${task.status}`],
    extendedProps: {
      task,
      status: task.status,
      priority: task.priority,
    },
  };
}

function eventContent({ event, timeText }: EventContentArg) {
  const task = event.extendedProps.task as Task | undefined;
  const status = task ? statusLabel(task.status) : "Task";
  const priority = task?.priority && task.priority !== "none"
    ? `${task.priority} priority`
    : "no priority";

  return (
    <div className="cortex-task-event__content">
      {timeText ? <span className="cortex-task-event__time">{timeText}</span> : null}
      <span className="cortex-task-event__title">{event.title}</span>
      <span className="sr-only">{status}, {priority}</span>
    </div>
  );
}

function eventLabel(task: Task) {
  const status = statusLabel(task.status);
  const priority = task.priority === "none" ? "no priority" : `${task.priority} priority`;
  return `${task.title}, ${status}, ${priority}`;
}

function TaskCalendarTooltip({ task }: { task: Task }) {
  const status = statusOption(task.status);
  const priority = priorityOption(task.priority);
  const StatusIcon = status.icon;
  const PriorityIcon = priority.icon;

  return (
    <div className="cortex-task-tooltip">
      <p className="truncate text-sm font-semibold text-foreground">{task.title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[0.68rem] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <StatusIcon aria-hidden="true" className={status.colorClass} />
          {status.label}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <PriorityIcon aria-hidden="true" className={priority.colorClass} />
          {priority.label}
        </span>
      </div>
      <div className="mt-2 space-y-1 border-t border-border/70 pt-2 font-mono text-[0.65rem] text-muted-foreground">
        {task.start_at ? <p>Starts · {formatDateTime(task.start_at)}</p> : null}
        {task.due_at ? <p>Due · {formatDateTime(task.due_at)}</p> : null}
      </div>
    </div>
  );
}

type TooltipListeners = {
  enter: () => void;
  leave: () => void;
  focus: () => void;
  blur: () => void;
};

type CreateTargetListeners = {
  keydown: (event: KeyboardEvent) => void;
};

function createTargetLabel(date: Date, allDay: boolean) {
  const dateLabel = new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);

  if (allDay) {
    return `Add task on ${dateLabel}`;
  }

  const timeLabel = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);

  return `Add task on ${dateLabel} at ${timeLabel}`;
}

function CalendarEmptyHint({ hasTasks }: { hasTasks: boolean }) {
  return (
    <div className="flex items-center gap-2 border-t border-border/70 px-4 py-3 text-xs text-muted-foreground">
      {hasTasks ? (
        <Clock3 aria-hidden="true" className="size-3.5 shrink-0" />
      ) : (
        <CalendarDays aria-hidden="true" className="size-3.5 shrink-0" />
      )}
      <span>
        {hasTasks
          ? "Tasks with more results can be loaded below."
          : "No scheduled tasks are visible in this range. Undated tasks remain in List view."}
      </span>
    </div>
  );
}

export function TaskCalendar({
  tasks,
  isPending,
  isFetching,
  hasNextPage,
  isFetchingNextPage,
  onFetchNextPage,
  onRangeChange,
  onOpenTask,
  onCreateTask,
}: TaskCalendarProps) {
  const initialDate = useMemo(() => new Date(), []);
  const [activeTooltip, setActiveTooltip] = useState<{
    task: Task;
    anchor: HTMLElement;
  } | null>(null);
  const tooltipTimer = useRef<number | null>(null);
  const tooltipListeners = useRef(new WeakMap<HTMLElement, TooltipListeners>());
  const createTargetListeners = useRef(new WeakMap<HTMLElement, CreateTargetListeners>());
  const events = useMemo(
    () => tasks.map(eventForTask).filter((event): event is EventInput => Boolean(event)),
    [tasks],
  );

  function handleDatesSet({ start, end }: DatesSetArg) {
    onRangeChange({ start, end });
  }

  const hideTooltip = useCallback(() => {
    if (tooltipTimer.current !== null) {
      window.clearTimeout(tooltipTimer.current);
      tooltipTimer.current = null;
    }

    setActiveTooltip((current) => {
      current?.anchor.removeAttribute("aria-describedby");
      return null;
    });
  }, []);

  const showTooltip = useCallback((task: Task, anchor: HTMLElement) => {
    if (tooltipTimer.current !== null) {
      window.clearTimeout(tooltipTimer.current);
    }

    tooltipTimer.current = window.setTimeout(() => {
      tooltipTimer.current = null;
      setActiveTooltip((current) => {
        current?.anchor.removeAttribute("aria-describedby");
        anchor.setAttribute("aria-describedby", `cortex-task-tooltip-${task.id}`);
        return { task, anchor };
      });
    }, 450);
  }, []);

  useEffect(() => {
    return () => {
      if (tooltipTimer.current !== null) {
        window.clearTimeout(tooltipTimer.current);
      }
    };
  }, []);

  function handleEventClick({ event, jsEvent }: EventClickArg) {
    jsEvent.preventDefault();
    hideTooltip();
    const task = event.extendedProps.task as Task | undefined;
    if (task) {
      onOpenTask(task);
    }
  }

  function mountCreateTarget(el: HTMLElement, date: Date, allDay: boolean) {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest(".fc-event")) {
        return;
      }

      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      hideTooltip();
      onCreateTask({ date, allDay });
    };

    el.classList.add("cortex-calendar__create-target");
    el.setAttribute("role", "button");
    el.setAttribute("tabindex", "0");
    el.setAttribute("aria-label", createTargetLabel(date, allDay));
    el.addEventListener("keydown", keydown);
    createTargetListeners.current.set(el, { keydown });
  }

  function unmountCreateTarget(el: HTMLElement) {
    const listeners = createTargetListeners.current.get(el);
    if (listeners) {
      el.removeEventListener("keydown", listeners.keydown);
      createTargetListeners.current.delete(el);
    }

    el.classList.remove("cortex-calendar__create-target");
    el.removeAttribute("role");
    el.removeAttribute("tabindex");
    el.removeAttribute("aria-label");
  }

  function handleDateClick({ date, allDay }: DateClickArg) {
    hideTooltip();
    onCreateTask({ date, allDay });
  }

  return (
    <div className="mt-4 space-y-3">
      <Card
        className="cortex-calendar relative overflow-hidden rounded-xl border-border/80 bg-card p-3 shadow-none sm:p-4"
        aria-busy={isPending || isFetching}
      >
        <div className="sr-only" aria-live="polite">
          {isFetching ? "Loading scheduled tasks" : `${events.length} scheduled tasks visible`}
        </div>
        <TooltipProvider delay={450} closeDelay={0}>
          <div className="min-w-0 overflow-x-auto">
            <div className="min-w-[42rem] sm:min-w-0">
              <FullCalendar
              plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
              initialView="dayGridMonth"
              initialDate={initialDate}
              headerToolbar={{
                left: "prev,next today",
                center: "title",
                right: "dayGridMonth,timeGridWeek",
              }}
              buttonText={{ today: "Today", month: "Month", week: "Week" }}
              events={events}
              eventContent={eventContent}
              dateClick={handleDateClick}
              eventClick={handleEventClick}
              eventClassNames={({ event }) => {
                const task = event.extendedProps.task as Task | undefined;
                return task ? [`cortex-task-event--${task.status}`] : [];
              }}
              eventDidMount={({ event, el }) => {
                const task = event.extendedProps.task as Task | undefined;
                if (task) {
                  el.setAttribute("aria-label", eventLabel(task));
                  el.removeAttribute("title");

                  const listeners: TooltipListeners = {
                    enter: () => showTooltip(task, el),
                    leave: hideTooltip,
                    focus: () => showTooltip(task, el),
                    blur: hideTooltip,
                  };
                  tooltipListeners.current.set(el, listeners);
                  el.addEventListener("mouseenter", listeners.enter);
                  el.addEventListener("mouseleave", listeners.leave);
                  el.addEventListener("focus", listeners.focus);
                  el.addEventListener("blur", listeners.blur);
                }
              }}
              eventWillUnmount={({ el }) => {
                const listeners = tooltipListeners.current.get(el);
                if (!listeners) {
                  return;
                }

                el.removeEventListener("mouseenter", listeners.enter);
                el.removeEventListener("mouseleave", listeners.leave);
                el.removeEventListener("focus", listeners.focus);
                el.removeEventListener("blur", listeners.blur);
                tooltipListeners.current.delete(el);
                if (activeTooltip?.anchor === el) {
                  hideTooltip();
                }
              }}
              dayCellDidMount={({ el, date }) => {
                mountCreateTarget(el, date, true);
              }}
              dayCellWillUnmount={({ el }) => {
                unmountCreateTarget(el);
              }}
              dayHeaderDidMount={({ el, date }) => {
                mountCreateTarget(el, date, true);
              }}
              dayHeaderWillUnmount={({ el }) => {
                unmountCreateTarget(el);
              }}
              slotLaneDidMount={({ el, date }) => {
                if (date) {
                  mountCreateTarget(el, date, false);
                }
              }}
              slotLaneWillUnmount={({ el }) => {
                unmountCreateTarget(el);
              }}
              datesSet={handleDatesSet}
              editable={false}
              selectable={false}
              dayMaxEvents={3}
              expandRows
              nowIndicator
              slotMinTime="06:00:00"
              slotMaxTime="24:00:00"
              allDaySlot
              height="auto"
              contentHeight="auto"
              fixedWeekCount={false}
              weekends
              eventDisplay="block"
              />
            </div>
          </div>
          {activeTooltip ? (
            <Tooltip
              open
              disableHoverablePopup
              onOpenChange={(open) => {
                if (!open) {
                  hideTooltip();
                }
              }}
            >
              <TooltipContent
                id={`cortex-task-tooltip-${activeTooltip.task.id}`}
                anchor={activeTooltip.anchor}
                className="cortex-task-tooltip__content"
              >
                <TaskCalendarTooltip task={activeTooltip.task} />
              </TooltipContent>
            </Tooltip>
          ) : null}
        </TooltipProvider>
        {isPending && !tasks.length ? (
          <div className="pointer-events-none absolute inset-x-3 top-16 bottom-3 rounded-lg bg-card/65 sm:inset-x-4" />
        ) : null}
        {hasNextPage ? (
          <div className="flex justify-center border-t border-border/70 pt-3">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-xs text-primary-strong"
              onClick={onFetchNextPage}
              disabled={isFetchingNextPage}
            >
              {isFetchingNextPage ? "Loading more scheduled tasks…" : "Load more scheduled tasks"}
            </Button>
          </div>
        ) : null}
        {!isPending && !isFetching && !events.length && !hasNextPage ? (
          <CalendarEmptyHint hasTasks={tasks.length > 0} />
        ) : null}
      </Card>
    </div>
  );
}
