import Link from "next/link";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/report", label: "Report hazard" },
  { href: "/briefings", label: "Briefings" },
];

export function Nav() {
  return (
    <header className="border-b border-neutral-200 bg-white">
      <nav className="mx-auto flex max-w-6xl items-center gap-4 overflow-x-auto px-4 py-3 sm:gap-6">
        <Link href="/" className="whitespace-nowrap font-semibold">
          PlanIT Control
        </Link>
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className="whitespace-nowrap text-sm text-neutral-600 hover:text-neutral-900">
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
