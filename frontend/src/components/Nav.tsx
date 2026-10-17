import Link from "next/link";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/report", label: "Report hazard" },
  { href: "/briefings", label: "Briefings" },
];

export function Nav() {
  return (
    <header className="border-b border-neutral-200 bg-white">
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="font-semibold">
          PlanIT Control
        </Link>
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className="text-sm text-neutral-600 hover:text-neutral-900">
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
