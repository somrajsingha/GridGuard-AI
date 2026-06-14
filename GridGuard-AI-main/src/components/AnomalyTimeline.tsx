import { AlertCircle, Clock } from "lucide-react";
import { useRef, useEffect } from "react";

interface Event {
  id: string;
  time: string;
  house: string;
  reason: string;
  severity: number;
  zone: string;
}

export default function AnomalyTimeline({ events }: { events: Event[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [events.length]);

  const severityColor = (s: number) =>
    s >= 80 ? "text-red-400" : s >= 65 ? "text-orange-400" : "text-yellow-400";

  const dotColor = (s: number) =>
    s >= 80
      ? "bg-red-500 shadow-[0_0_10px_3px_rgba(239,68,68,0.6)]"
      : s >= 65
      ? "bg-orange-500 shadow-[0_0_10px_3px_rgba(249,115,22,0.5)]"
      : "bg-yellow-400 shadow-[0_0_10px_3px_rgba(234,179,8,0.5)]";

  const severityBg = (s: number) =>
    s >= 80
      ? "hover:bg-red-500/5"
      : s >= 65
      ? "hover:bg-orange-500/5"
      : "hover:bg-yellow-500/5";

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-9 h-9 rounded-lg bg-destructive/20 border border-destructive/40 flex items-center justify-center">
          <Clock className="w-4 h-4 text-destructive" />
        </div>
        <div>
          <h3 className="font-semibold">Anomaly Timeline</h3>
          <p className="text-xs text-muted-foreground">Real-time suspicious events</p>
        </div>
        {events.length > 0 && (
          <span className="ml-auto text-[10px] font-bold px-2 py-0.5 rounded-full bg-destructive/20 text-destructive border border-destructive/30">
            {events.length}
          </span>
        )}
      </div>

      {/* Scroll container — position:relative establishes the stacking context */}
      <div
        ref={scrollRef}
        className="timeline-scroll relative max-h-[260px] overflow-y-auto pr-1"
      >
        {/* Vertical connector line — z-0 so dots always render above it */}
        <div
          aria-hidden="true"
          className="absolute top-0 bottom-0 z-0 w-px bg-gradient-to-b from-primary/50 via-primary/20 to-transparent"
          style={{ left: "5px" }}
        />

        {events.length === 0 && (
          <div className="pl-8 py-4 text-xs text-muted-foreground italic text-center">
            No anomalies detected.
          </div>
        )}

        <div className="space-y-1">
          {events.map((e, idx) => (
            <div
              key={e.id}
              className={`relative pl-8 rounded-lg ${severityBg(e.severity)} transition-all duration-200 py-2 pr-2 animate-slide-in-right`}
              style={{ animationDelay: `${idx * 40}ms` }}
            >
              {/*
                Dot: position is relative to the event row.
                left: -20px puts it at roughly column 5px of the scroll container
                (row has pl-8 = 32px, so left:-27px centers on the line at 5px)
              */}
              <div
                className={`absolute z-10 w-3 h-3 rounded-full ${dotColor(e.severity)} animate-pulse`}
                style={{ left: "-1px", top: "14px" }}
              />

              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[10px] text-muted-foreground/70 tracking-wide">
                    {e.time} · <span className="text-primary/70">{e.zone}</span>
                  </div>
                  <div className="text-sm font-semibold truncate mt-0.5">{e.house}</div>
                  <div className={`text-xs flex items-center gap-1 mt-0.5 ${severityColor(e.severity)}`}>
                    <AlertCircle className="w-3 h-3 shrink-0" />
                    <span className="truncate">{e.reason}</span>
                  </div>
                </div>
                <div className={`text-xs font-bold shrink-0 tabular-nums ${severityColor(e.severity)}`}>
                  {e.severity}<span className="text-[10px] text-muted-foreground/60">/100</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Bottom fade mask when list overflows */}
        {events.length > 3 && (
          <div
            className="sticky bottom-0 left-0 right-0 h-6 pointer-events-none"
            style={{ background: "linear-gradient(to top, hsl(222 40% 12% / 0.95), transparent)" }}
          />
        )}
      </div>
    </div>
  );
}
