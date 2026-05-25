import Image from "next/image";

interface LogoProps {
  size?: number;
  showWordmark?: boolean;
}

/** Official X mark + wordmark. Mark sits on its own dark tile (Cobalt-family). */
export function Logo({ size = 30, showWordmark = true }: LogoProps) {
  return (
    <span className="brand">
      <Image
        src="/x-mark.png"
        alt="XPrediction"
        width={size}
        height={size}
        className="logo-mark"
        priority
      />
      {showWordmark && (
        <span className="wordmark">
          <i>X</i>Prediction
        </span>
      )}
    </span>
  );
}
