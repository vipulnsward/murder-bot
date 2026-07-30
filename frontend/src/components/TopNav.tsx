import { Link, NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Home" },
  { to: "/counter", label: "Counter" },
  { to: "/intel", label: "Intel" },
];

export function TopNav() {
  return (
    <header className="relative z-50 border-b border-gold/20 bg-[rgba(12,9,5,.9)] backdrop-blur">
      <div className="mx-auto flex h-16 w-[min(1000px,92vw)] items-center justify-between gap-4">
        <Link to="/" className="font-display text-lg font-extrabold text-gold-gradient">
          Murder Bot
        </Link>
        <nav aria-label="Primary navigation" className="flex items-center gap-1">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                `rounded-lg px-3 py-2 text-sm font-bold transition-colors ${
                  isActive
                    ? "bg-gold/15 text-gold-bright"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
