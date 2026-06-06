/**
 * BetPlacedSuccess — the "bet placed" confirmation with a bit of weight
 * (v1.1 Fase C / C4). Replaces the flat inline green line: a spring-animated
 * check + the message. This renders only AFTER the user confirms a bet (the
 * page is active), so animating opacity/scale here is safe — no SSR/invisible
 * concern. Green is semantic (success), not the brand color.
 */
"use client";

import { motion } from "framer-motion";
import { Check } from "lucide-react";

export function BetPlacedSuccess({ message }: { message: string }) {
  return (
    <motion.div
      role="status"
      data-testid="bet-success"
      className="flex items-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/10 p-3 text-sm font-semibold text-emerald-400"
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      <motion.span
        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white"
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: "spring", stiffness: 500, damping: 18, delay: 0.05 }}
      >
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
      </motion.span>
      <span>{message}</span>
    </motion.div>
  );
}
