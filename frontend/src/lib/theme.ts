// White-label tenant presets. The accent + logo are the only things a tenant
// swaps; the rest of the system is neutral. Override --accent on any subtree to
// retheme it at runtime (proven in the White-label section).

export interface Tenant {
  id: string;
  name: string;
  /** Rendered with the first segment in accent color. */
  nameLead: string;
  nameRest: string;
  accent: string;
  accentSoft: string;
  logo: "x" | "check";
  tag: string;
}

export const tenants: Tenant[] = [
  {
    id: "xprediction",
    name: "XPrediction",
    nameLead: "X",
    nameRest: "Prediction",
    accent: "#4f76e8",
    accentSoft: "rgba(79, 118, 232, 0.16)",
    logo: "x",
    tag: "tenant · default",
  },
  {
    id: "northwind",
    name: "Northwind",
    nameLead: "North",
    nameRest: "wind",
    accent: "#22b07d",
    accentSoft: "rgba(34, 176, 125, 0.16)",
    logo: "check",
    tag: "tenant · rebranded",
  },
];
