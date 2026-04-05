import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = { title: "Ghost" };

const NAV = [
  { href: "/", label: "Home" },
  { href: "/conversations", label: "Conversations" },
  { href: "/contacts", label: "Contacts" },
  { href: "/mood", label: "Mood" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex">
        <aside className="w-44 shrink-0 border-r border-zinc-800 flex flex-col pt-6 px-3 gap-1">
          <div className="px-2 mb-4 text-violet-400 font-mono text-sm font-semibold tracking-widest">
            👻 GHOST
          </div>
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="px-2 py-1.5 rounded text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 text-sm transition-colors"
            >
              {n.label}
            </Link>
          ))}
        </aside>
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </body>
    </html>
  );
}
