import { Logo } from "@/components/ui/Logo";

const links = ["Markets", "Experimental", "Infrastructure"];

export function Footer() {
  return (
    <footer>
      <div className="wrap">
        <div className="fmin">
          <div className="fbrand">
            <Logo />
            <p>The prediction layer for the real world.</p>
          </div>
          <div className="flinks">
            {links.map((l) => (
              <a key={l} href="#">
                {l}
              </a>
            ))}
          </div>
        </div>
        <div className="fbot">
          <span>© 2026 XPrediction</span>
          <span>Play money · no real wagering</span>
        </div>
      </div>
    </footer>
  );
}
