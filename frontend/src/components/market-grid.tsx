/**
 * MarketGrid — staggers the market cards in on mount (v1.1 Fase C / C2).
 *
 * The Server Component (market-list) fetches and passes the cards as children;
 * this client wrapper only owns the grid layout + their entrance animation.
 *
 * Robustness: the entrance animates `y` + a hair of `scale` but NEVER `opacity`
 * — so cards stay fully visible even if JS is slow to hydrate or the tab is
 * backgrounded (they just settle in from 10px lower). And `useReducedMotion`
 * skips the entrance entirely for users who ask for less motion.
 */
"use client";

import { Children } from "react";
import { motion, useReducedMotion, type Variants } from "framer-motion";

const container: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.05 } },
};

const item: Variants = {
  hidden: { y: 10, scale: 0.99 },
  show: { y: 0, scale: 1, transition: { duration: 0.3, ease: "easeOut" } },
};

export function MarketGrid({ children }: { children: React.ReactNode }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3"
      variants={container}
      initial={reduceMotion ? false : "hidden"}
      animate="show"
    >
      {Children.map(children, (child) => (
        <motion.div variants={item}>{child}</motion.div>
      ))}
    </motion.div>
  );
}
