import type { Tenant } from "@/lib/theme";

function TenantGlyph({ logo }: { logo: Tenant["logo"] }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.4,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (logo === "check") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" />
        <path d="M8 12.5 11 15.5 16 9" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M5 17.5 L11 10.5" />
      <path d="M13.2 14 L19 6.8" />
      <circle cx="12" cy="12.2" r="1.7" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function TenantPreview({ tenant }: { tenant: Tenant }) {
  const style = {
    "--accent": tenant.accent,
    "--accent-soft": tenant.accentSoft,
  } as React.CSSProperties;

  return (
    <div className="tenant" style={style}>
      <div className="tbar">
        <div className="lt">
          <TenantGlyph logo={tenant.logo} />
        </div>
        <span className="nm">
          <span style={{ color: "var(--accent)" }}>{tenant.nameLead}</span>
          {tenant.nameRest}
        </span>
        <span className="tag">{tenant.tag}</span>
      </div>
      <div className="tbody">
        <div className="mini">
          <span className="mq">Will the Fed cut rates in March 2026?</span>
          <span className="mp">64%</span>
        </div>
        <div className="mtrack">
          <i style={{ width: "64%" }} />
        </div>
        <div className="mbtn">Trade Yes · 64¢</div>
      </div>
    </div>
  );
}
