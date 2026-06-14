/**
 * AIExplanationPanel
 * ──────────────────
 * Displays the OpenAI-powered explanation for a selected house.
 * Features: typing animation, keyword highlighting, confidence badge,
 *           loading skeleton, graceful fallback to rule-based reason.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import {
  Brain,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ChevronRight,
  Loader2,
  Zap,
  Wrench,
  ShieldCheck,
} from "lucide-react";
import type { House } from "@/lib/gridData";

// ─── Types ───────────────────────────────────────────────────────────────────
interface ExplanationResult {
  house_id: number;
  ai_explanation: string;
  solution: string;
  source: "openai" | "gemini" | "fallback";
}

interface Props {
  house: House | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
const HIGHLIGHT_KEYWORDS = [
  "spike",
  "night usage",
  "meter bypass",
  "tampering",
  "overload",
  "mismatch",
  "anomaly",
  "suspicious",
  "illegal",
  "bypass",
  "abnormal",
  "unauthorized",
  "inspect",
  "disconnect",
  "investigate",
  "audit",
  "immediate",
  "critical",
  "high risk",
  "load share",
];

function highlightText(text: string): React.ReactNode[] {
  const pattern = new RegExp(`(${HIGHLIGHT_KEYWORDS.join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    if (pattern.test(part)) {
      return (
        <mark
          key={i}
          className="bg-primary/20 text-primary rounded px-0.5 font-semibold not-italic"
        >
          {part}
        </mark>
      );
    }
    return part;
  });
}

function confidenceBadge(score: number) {
  if (score >= 80)
    return {
      label: "Very High Confidence",
      cls: "bg-destructive/20 border-destructive/50 text-destructive",
      icon: AlertTriangle,
    };
  if (score >= 65)
    return {
      label: "High Confidence",
      cls: "bg-orange-500/20 border-orange-500/50 text-orange-400",
      icon: AlertTriangle,
    };
  if (score >= 35)
    return {
      label: "Medium Confidence",
      cls: "bg-warning/20 border-warning/50 text-warning",
      icon: Clock,
    };
  return {
    label: "Low Confidence",
    cls: "bg-success/20 border-success/50 text-success",
    icon: CheckCircle2,
  };
}

function riskColor(level: House["risk_level"]) {
  return level === "high"
    ? "text-destructive"
    : level === "medium"
      ? "text-warning"
      : "text-success";
}

function riskBg(level: House["risk_level"]) {
  return level === "high"
    ? "bg-destructive/10 border-destructive/30"
    : level === "medium"
      ? "bg-warning/10 border-warning/30"
      : "bg-success/10 border-success/30";
}

// ─── Typing animation hook ───────────────────────────────────────────────────
function useTypingAnimation(text: string, active: boolean) {
  const [displayed, setDisplayed] = useState("");
  const indexRef = useRef(0);

  useEffect(() => {
    if (!active || !text) {
      setDisplayed(text);
      return;
    }
    setDisplayed("");
    indexRef.current = 0;
    const interval = setInterval(() => {
      if (indexRef.current < text.length) {
        setDisplayed(text.slice(0, indexRef.current + 1));
        indexRef.current++;
      } else {
        clearInterval(interval);
      }
    }, 12); // ~12ms per char — fast but visible
    return () => clearInterval(interval);
  }, [text, active]);

  return displayed;
}

// ─── Cache (module-level, 5-min TTL) ─────────────────────────────────────────
const _cache = new Map<number, { result: ExplanationResult; at: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function fetchExplanation(houseId: number): Promise<ExplanationResult> {
  const cached = _cache.get(houseId);
  if (cached && Date.now() - cached.at < CACHE_TTL) {
    return cached.result;
  }
  const res = await fetch(`/api/explanation?house_id=${houseId}`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  const data: ExplanationResult = await res.json();
  _cache.set(houseId, { result: data, at: Date.now() });
  return data;
}

// ─── Component ───────────────────────────────────────────────────────────────
export default function AIExplanationPanel({ house }: Props) {
  const [explanation, setExplanation] = useState<ExplanationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [animating, setAnimating] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const displayedText = useTypingAnimation(
    explanation?.ai_explanation ?? "",
    animating
  );

  const load = useCallback(async (h: House) => {
    // Cancel any in-flight request
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setLoading(true);
    setError(null);
    setExplanation(null);
    setAnimating(false);

    try {
      const result = await fetchExplanation(h.house_id);
      setExplanation(result);
      setAnimating(true); // start typing animation
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      // Graceful fallback — build client-side solution hint from primary reason
      const primary = h.reason.primary.toLowerCase();
      let fallbackSolution = "";
      if (primary.includes("bypass") || primary.includes("tamper")) {
        fallbackSolution = "Replace meter with a tamper-proof smart meter, install CT clamp for cross-validation, and file FIR if bypass is physically confirmed.";
      } else if (primary.includes("night")) {
        fallbackSolution = "Deploy smart meter with Time-of-Use tariff, install load-limiter relay for night-time alerts, and inspect for illegal sub-connections.";
      } else if (primary.includes("mismatch") || primary.includes("load")) {
        fallbackSolution = "Conduct transformer energy audit, upgrade to IoT-enabled transformer monitor, and map all feeder connections for unregistered consumers.";
      } else if (primary.includes("spike") || primary.includes("peak")) {
        fallbackSolution = "Install waveform-logging analyser, cross-reference spikes with external data, and issue show-cause notice for unexplained anomalies.";
      } else if (primary.includes("phase") || primary.includes("imbalance")) {
        fallbackSolution = "Inspect phase connections, upgrade to 3-phase smart meter with per-phase logging, and seal terminal blocks with tamper-evident epoxy.";
      } else {
        fallbackSolution = "Verify meter seal integrity, compare physical appliance load vs recorded demand, and replace with certified smart meter if discrepancies persist.";
      }
      const fallback: ExplanationResult = {
        house_id: h.house_id,
        ai_explanation:
          `House #${h.house_id} shows ${h.reason.primary}` +
          (h.reason.secondary.length
            ? ` with secondary indicators: ${h.reason.secondary.join(", ")}.`
            : ".") +
          ` Risk score: ${h.risk_score}/100 (${h.risk_level} risk). Zone: ${h.zone}. Recommended action: Schedule inspection.`,
        solution: fallbackSolution,
        source: "fallback",
      };
      setExplanation(fallback);
      setAnimating(true);
      setError("AI backend unavailable — showing rule-based analysis");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!house) {
      setExplanation(null);
      setError(null);
      setAnimating(false);
      return;
    }
    // Debounce rapid house selections (300 ms)
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => load(house), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [house, load]);

  // ── Empty state ──
  if (!house) {
    return (
      <div className="glass rounded-2xl p-5 border border-border/50">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-600 to-primary flex items-center justify-center shrink-0">
            <Brain className="w-4 h-4 text-white" />
          </div>
          <div>
            <h3 className="font-semibold text-sm flex items-center gap-1.5">
              AI Explanation
              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-primary/20 text-primary border border-primary/30">
                Gemini
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              OpenAI-powered insight per house
            </p>
          </div>
        </div>
        <div className="flex flex-col items-center justify-center py-8 gap-3 text-center">
          <div className="w-12 h-12 rounded-full bg-secondary/50 flex items-center justify-center">
            <Sparkles className="w-5 h-5 text-muted-foreground" />
          </div>
          <p className="text-sm text-muted-foreground max-w-[200px]">
            Click any house on the map or priority list to generate an AI explanation
          </p>
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground/60">
            <Zap className="w-3 h-3" />
            On-demand · Cached 5 min
          </div>
        </div>
      </div>
    );
  }

  const badge = confidenceBadge(house.risk_score);
  const BadgeIcon = badge.icon;
  const isTypingDone =
    !animating ||
    (explanation && displayedText === explanation.ai_explanation);

  // ── Extract "action" sentence only for high/medium risk ──
  const rawText = explanation?.ai_explanation ?? "";
  const sentences = rawText
    .replace(/\n/g, " ")
    .split(/(?<=[.!?])\s+/)
    .filter(Boolean);

  // Only surface an action sentence for high or medium risk houses
  const isHighOrMedium = house.risk_level === "high" || house.risk_level === "medium";
  const actionIdx = isHighOrMedium
    ? sentences.findIndex((s) =>
      /inspect|disconnect|audit|investigat|field|schedul|immediate|verify|action|recommend/i.test(s)
    )
    : -1;
  const actionSentence =
    isHighOrMedium && actionIdx !== -1
      ? sentences[actionIdx]
      : "";

  // Action box label depends on risk level
  const actionLabel =
    house.risk_level === "high"
      ? "Immediate Action Required"
      : house.risk_level === "medium"
        ? "Recommended Action"
        : "";

  const bodyText =
    actionIdx !== -1
      ? sentences.slice(0, actionIdx).join(" ") +
      (actionIdx > 0 && sentences.length > actionIdx + 1
        ? " " + sentences.slice(actionIdx + 1).join(" ")
        : "")
      : sentences.join(" ");

  return (
    <div className="glass rounded-2xl p-5 border border-border/50 space-y-4">
      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-600 to-primary flex items-center justify-center shrink-0 relative">
            <Brain className="w-4 h-4 text-white" />
            {loading && (
              <span className="absolute inset-0 rounded-lg border-2 border-primary animate-spin border-t-transparent" />
            )}
          </div>
          <div>
            <h3 className="font-semibold text-sm flex items-center gap-1.5">
              AI Explanation
              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-primary/20 text-primary border border-primary/30">
                GPT-4.1
              </span>
            </h3>
            <p className="text-xs text-muted-foreground">
              House #{house.house_id}
            </p>
          </div>
        </div>

        {/* Confidence badge */}
        <div
          className={`flex items-center gap-1 px-2 py-1 rounded-full border text-[10px] font-semibold ${badge.cls}`}
        >
          <BadgeIcon className="w-3 h-3" />
          {house.risk_score}/100
        </div>
      </div>

      {/* ── Risk level strip ── */}
      <div className={`rounded-xl border px-3 py-2 flex items-center justify-between ${riskBg(house.risk_level)}`}>
        <div className="flex items-center gap-2">
          <AlertTriangle className={`w-3.5 h-3.5 ${riskColor(house.risk_level)}`} />
          <span className={`text-xs font-bold uppercase tracking-wide ${riskColor(house.risk_level)}`}>
            {house.risk_level} risk
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground">{house.zone}</span>
      </div>

      {/* ── Loading state ── */}
      {loading && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-primary">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span className="animate-pulse">Generating AI insight...</span>
          </div>
          <div className="space-y-1.5">
            {[100, 85, 70, 55].map((w) => (
              <div
                key={w}
                className="animate-pulse h-3 rounded-full bg-secondary/60"
                style={{ width: `${w}%` }}
              />
            ))}
          </div>
        </div>
      )}

      {/* ── Error / fallback notice ── */}
      {error && !loading && (
        <div className="flex items-center gap-2 text-[10px] text-warning bg-warning/10 border border-warning/20 rounded-lg px-2.5 py-1.5">
          <AlertTriangle className="w-3 h-3 shrink-0" />
          {error}
        </div>
      )}

      {/* ── Explanation body ── */}
      {!loading && explanation && (
        <div className="space-y-3">
          {/* Main explanation with typing animation */}
          <div className="text-xs leading-relaxed text-foreground/90 min-h-[60px]">
            {/* Show highlighted text when done typing, plain during animation */}
            {isTypingDone ? (
              <span>{highlightText(rawText)}</span>
            ) : (
              <span>
                {displayedText}
                <span className="inline-block w-0.5 h-3.5 bg-primary ml-0.5 animate-pulse" />
              </span>
            )}
          </div>

          {/* Recommended action box — only for high/medium risk */}
          {actionSentence && actionLabel ? (
            <div className={`rounded-xl p-3 space-y-1 border ${house.risk_level === "high"
                ? "bg-destructive/8 border-destructive/25"
                : "bg-warning/8 border-warning/25"
              }`}>
              <div className={`flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide ${house.risk_level === "high" ? "text-destructive" : "text-warning"
                }`}>
                <ChevronRight className="w-3 h-3" />
                {actionLabel}
              </div>
              <p className="text-xs text-foreground/85 leading-relaxed">
                {highlightText(actionSentence)}
              </p>
            </div>
          ) : house.risk_level === "low" ? (
            <div className="rounded-xl bg-success/8 border border-success/25 p-3 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
              <p className="text-xs text-success/90 font-medium">No Immediate Action Required — continue monitoring over the next 30 days.</p>
            </div>
          ) : null}

          {/* Solution card */}
          {explanation.solution && (
            <div className="rounded-xl bg-emerald-500/8 border border-emerald-500/25 p-3 space-y-1.5">
              <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-semibold uppercase tracking-wide">
                <Wrench className="w-3 h-3" />
                Recommended Solution
              </div>
              <p className="text-xs text-foreground/85 leading-relaxed">
                {explanation.solution.split(/\.\s+/).map((sentence, i, arr) => (
                  <span key={i}>
                    <span className="inline-flex items-start gap-1.5">
                      <ShieldCheck className="w-3 h-3 text-emerald-400 mt-0.5 shrink-0" />
                      <span>{sentence}{i < arr.length - 1 ? "." : ""}</span>
                    </span>
                    {i < arr.length - 1 && <span className="block mt-1" />}
                  </span>
                ))}
              </p>
            </div>
          )}

          {/* Metrics strip */}
          <div className="grid grid-cols-3 gap-2">
            {[
              {
                label: "Avg kWh",
                value: house.average_consumption.toFixed(1),
              },
              {
                label: "Night Ratio",
                value: `${(house.night_usage_ratio * 100).toFixed(0)}%`,
              },
              {
                label: "Load Share",
                value: `${(house.transformer_load_share * 100).toFixed(0)}%`,
              },
            ].map((m) => (
              <div
                key={m.label}
                className="rounded-lg bg-secondary/40 border border-border/50 p-2 text-center"
              >
                <div className="text-sm font-bold text-foreground">
                  {m.value}
                </div>
                <div className="text-[9px] text-muted-foreground">
                  {m.label}
                </div>
              </div>
            ))}
          </div>

          {/* Source badge */}
          <div className="flex items-center justify-between text-[9px] text-muted-foreground/50">
            <span className="flex items-center gap-1">
              <Sparkles className="w-2.5 h-2.5" />
              {explanation.source === "openai" || explanation.source === "gemini"
                ? "Generated by Gemini 2.5 Flash · Cached 5 min"
                : "Rule-based fallback"}
            </span>
            <span>{badge.label}</span>
          </div>
        </div>
      )}
    </div>
  );
}
