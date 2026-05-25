import { Logo } from "@/components/ui/Logo";
import { navLinks } from "@/lib/mock-data";

export function Navbar() {
  return (
    <header className="nav">
      <div className="nav-in">
        <Logo />
        <nav className="nav-links">
          {navLinks.map((l) => (
            <a key={l} href="#">
              {l}
            </a>
          ))}
        </nav>
        <div className="nav-sp" />
        <span className="nav-sign">Sign in</span>
        <a className="nav-cta" href="#">
          Get access
        </a>
      </div>
    </header>
  );
}
