import { tenants } from "@/lib/theme";
import { TenantPreview } from "./TenantPreview";

type FeatureIcon = "tokens" | "clock" | "layers";

const features: { title: string; body: string; icon: FeatureIcon }[] = [
  {
    title: "Design tokens",
    body: "Color, type and spacing flow from one token layer. Rebrand once, propagate everywhere.",
    icon: "tokens",
  },
  {
    title: "Runtime theming",
    body: "Tenants swap logo and accent live — no rebuild, no redeploy.",
    icon: "clock",
  },
  {
    title: "Multi-tenant",
    body: "Isolated data and config per brand, one shared core to maintain.",
    icon: "layers",
  },
];

function FeatureIcon({ name }: { name: FeatureIcon }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (name) {
    case "tokens":
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <circle cx="6" cy="6" r="2" />
          <circle cx="18" cy="18" r="2" />
        </svg>
      );
    case "clock":
      return (
        <svg {...common}>
          <path d="M12 3a9 9 0 1 0 9 9" />
          <path d="M12 7v5l3 2" />
        </svg>
      );
    case "layers":
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="6" rx="1.5" />
          <rect x="3" y="14" width="18" height="6" rx="1.5" />
        </svg>
      );
  }
}

export function WhiteLabel() {
  return (
    <section className="wl">
      <div className="wrap">
        <div className="shead">
          <div>
            <div className="eyebrow">Infrastructure</div>
            <h2>Your brand. Our rails.</h2>
            <p>
              The same platform, rendered for any tenant. Logo and accent are
              runtime tokens — the structure never changes.
            </p>
          </div>
        </div>
        <div className="tenants">
          {tenants.map((t) => (
            <TenantPreview key={t.id} tenant={t} />
          ))}
        </div>
        <div className="wlf">
          {features.map((f) => (
            <div className="f" key={f.title}>
              <div className="ic">
                <FeatureIcon name={f.icon} />
              </div>
              <h4>{f.title}</h4>
              <p>{f.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
