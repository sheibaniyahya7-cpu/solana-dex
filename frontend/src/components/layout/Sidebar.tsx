"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Coins, Wallet, TrendingUp,
  Fish, Bot, Bell, Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/tokens", label: "Tokens", icon: Coins },
  { href: "/wallets", label: "Wallets", icon: Wallet },
  { href: "/whales", label: "Whale Activity", icon: Fish },
  { href: "/analysis", label: "AI Analysis", icon: Bot },
  { href: "/alerts", label: "Alerts", icon: Bell },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 shrink-0 bg-surface border-r border-border flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
            <Activity className="w-4 h-4 text-primary" />
          </div>
          <div>
            <div className="text-text-primary font-bold text-sm leading-tight">DEX Trader</div>
            <div className="text-text-muted text-xs">AI Intelligence</div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                active
                  ? "bg-primary/15 text-primary border border-primary/20"
                  : "text-text-secondary hover:text-text-primary hover:bg-surface-2",
              )}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-border">
        <div className="text-text-muted text-xs">
          <div className="font-medium text-text-secondary mb-0.5">Solana DEX Trader</div>
          <div>v1.0.0 — Real-time AI</div>
        </div>
      </div>
    </aside>
  );
}
