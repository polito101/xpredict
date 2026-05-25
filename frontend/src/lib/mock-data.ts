// Static sample data for the product preview (pre-launch).
// No backend yet — wire real markets through src/lib/api.ts to replace these.
// Nothing here represents real volume, traders, or live activity.

export type MarketStatus = "live" | "closing";

export interface Market {
  id: string;
  category: string;
  question: string;
  probability: number; // 0-100
  delta: number; // signed pts
  status: MarketStatus;
  closeLabel?: string;
}

export interface ExperimentalMarket {
  id: string;
  icon: "traffic" | "weather" | "logistics" | "grid";
  question: string;
  value: string; // big number (count or %)
  valueLabel: string;
  probability: number;
  source: string;
  spark: number[]; // y values 0-30 (lower = higher on chart)
}

export interface ActivityItem {
  id: string;
  user: string;
  action: "yes" | "no" | "opened" | "resolved";
  detail: string;
  ts: string;
}

export interface Forecaster {
  rank: number;
  user: string;
  initials: string;
  resolved: number;
  streak: number;
  accuracy: number;
}

export interface TickerItem {
  label: string;
  prob: number;
  delta: number;
}

export const heroMarket = {
  category: "Macro · Fed",
  question: "Will the Fed cut rates at its March 2026 meeting?",
  probability: 64,
  delta: 3.2,
};

// Product capabilities, not usage metrics — we don't fake traction pre-launch.
export const heroStats = [
  { value: "Aggregated", label: "world markets" },
  { value: "Real-world", label: "signal markets" },
  { value: "White-label", label: "infrastructure" },
];

// Example markets that illustrate the format — not live, no real volume/traders.
export const markets: Market[] = [
  { id: "fed-mar26", category: "Macro", question: "Will the Fed cut rates at its March 2026 meeting?", probability: 64, delta: 3.2, status: "live" },
  { id: "ctx-10m", category: "AI", question: "Will a frontier model exceed a 10M-token context window in 2026?", probability: 38, delta: 0.9, status: "live" },
  { id: "eu-ai-act", category: "Policy", question: "Will the EU pass the AI Liability Act in 2026?", probability: 56, delta: 1.1, status: "closing", closeLabel: "Closes Jun 2026" },
];

// Concept previews of the signal-driven direction. Signal labels are the *kind*
// of data source, not a live integration — these feeds are not wired yet.
export const experimentalMarkets: ExperimentalMarket[] = [
  { id: "i405-traffic", icon: "traffic", question: "Will more than 18,000 cars cross the I-405 Sepulveda Pass tonight?", value: "17,482", valueLabel: "sample signal count", probability: 72, source: "Traffic sensors", spark: [24, 20, 22, 14, 16, 9, 12, 5, 8] },
  { id: "la-heat", icon: "weather", question: "Will downtown Los Angeles hit 95°F at any point this week?", value: "33%", valueLabel: "chance of Yes", probability: 33, source: "Weather data", spark: [18, 16, 19, 15, 17, 13, 15, 11, 14] },
  { id: "port-la", icon: "logistics", question: "Will the Port of LA clear its container backlog by Friday?", value: "49%", valueLabel: "chance of Yes", probability: 49, source: "Logistics data", spark: [10, 13, 11, 16, 14, 18, 16, 20, 17] },
  { id: "caiso-grid", icon: "grid", question: "Will California grid demand exceed 45 GW today?", value: "61%", valueLabel: "chance of Yes", probability: 61, source: "Grid data", spark: [20, 17, 18, 12, 13, 10, 8, 9, 6] },
];

export const initialActivity: ActivityItem[] = [
  { id: "a1", user: "maria.eth", action: "yes", detail: "Fed cut · Mar '26", ts: "2s" },
  { id: "a2", user: "nova_fin", action: "opened", detail: "EU AI Act", ts: "14s" },
  { id: "a3", user: "jdoe", action: "no", detail: "BTC > $150k", ts: "31s" },
  { id: "a4", user: "quantkid", action: "resolved", detail: "GPT-6 ships in 2026", ts: "1m" },
  { id: "a5", user: "signal.dao", action: "yes", detail: "I-405 traffic", ts: "1m" },
];

export const leaderboard: Forecaster[] = [
  { rank: 1, user: "maria.eth", initials: "MK", resolved: 312, streak: 41, accuracy: 91.4 },
  { rank: 2, user: "quantkid", initials: "QK", resolved: 540, streak: 18, accuracy: 88.7 },
  { rank: 3, user: "nova_fin", initials: "NV", resolved: 221, streak: 12, accuracy: 86.2 },
  { rank: 4, user: "signal.dao", initials: "SD", resolved: 803, streak: 7, accuracy: 84.9 },
];

export const tickerItems: TickerItem[] = [
  { label: "Fed cuts rates · Mar '26", prob: 64, delta: 3.2 },
  { label: "BTC > $150k · 2026", prob: 41, delta: -1.8 },
  { label: "GPT-6 ships in 2026", prob: 38, delta: 0.9 },
  { label: "I-405 jams after 9pm", prob: 72, delta: 5.1 },
  { label: "EU AI Liability Act", prob: 56, delta: 1.1 },
  { label: "Real Madrid · UCL '26", prob: 22, delta: -0.4 },
];

// Pool for the hero preview's sample activity feed (illustrative, not real users).
export const heroFeedPool: { user: string; side: "yes" | "no"; amount: string }[] = [
  { user: "ada_q", side: "yes", amount: "$2,400" },
  { user: "lwang", side: "no", amount: "$760" },
  { user: "vega", side: "yes", amount: "$5,100" },
  { user: "noor", side: "yes", amount: "$980" },
  { user: "kestrel", side: "no", amount: "$1,340" },
  { user: "rin", side: "yes", amount: "$610" },
];

export const heroFeedInitial = [
  { user: "maria.eth", side: "yes" as const, amount: "$1,200", ts: "2s" },
  { user: "jdoe", side: "no" as const, amount: "$480", ts: "9s" },
  { user: "quantkid", side: "yes" as const, amount: "$3,050", ts: "21s" },
];

export const navLinks = ["Markets", "Experimental", "Infrastructure"];
