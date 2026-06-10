/**
 * Motion language — shared variants used across the dashboard.
 *
 * Principles:
 *  - Subtle, never bouncy. We're a terminal, not a marketing site.
 *  - Distance ≤ 8px on enter/exit; opacity does most of the work.
 *  - Stagger 30–50ms per child max — fast enough that the user perceives
 *    the layout as "settled" within ~250ms of route change.
 *  - Easing: a custom cubic that's slightly more "snap then settle" than
 *    the framer-motion default, so panels feel composed, not floaty.
 *
 * Usage:
 *   <motion.div variants={fadeUp} initial="hidden" animate="show" />
 *   <motion.div variants={staggerContainer} initial="hidden" animate="show">
 *     {items.map(i => <motion.div key={i} variants={fadeUp} />)}
 *   </motion.div>
 */

import type { Variants, Transition } from 'framer-motion';

export const easeStandard: Transition['ease'] = [0.22, 1, 0.36, 1];
export const easeEnter:    Transition['ease'] = [0.16, 1, 0.3, 1];
export const easeExit:     Transition['ease'] = [0.4, 0, 1, 1];

/** Fade + small lift. Default panel mount animation. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.32, ease: easeEnter } },
  exit:   { opacity: 0, y: -4, transition: { duration: 0.18, ease: easeExit } },
};

/** Pure fade — for things where motion would be distracting (text-only). */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  show:   { opacity: 1, transition: { duration: 0.28, ease: easeEnter } },
  exit:   { opacity: 0, transition: { duration: 0.15, ease: easeExit } },
};

/** Slight scale + fade — used for top-of-page hero stats / accent cards. */
export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.97 },
  show:   { opacity: 1, scale: 1, transition: { duration: 0.32, ease: easeEnter } },
  exit:   { opacity: 0, scale: 0.99, transition: { duration: 0.16, ease: easeExit } },
};

/** Horizontal slide for tab transitions. */
export const slideRight: Variants = {
  hidden: { opacity: 0, x: 16 },
  show:   { opacity: 1, x: 0, transition: { duration: 0.34, ease: easeEnter } },
  exit:   { opacity: 0, x: -8, transition: { duration: 0.18, ease: easeExit } },
};

/** Container that staggers its children. Pair with fadeUp on children. */
export const staggerContainer: Variants = {
  hidden: { opacity: 1 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.04,
      delayChildren:   0.05,
    },
  },
  exit: {
    transition: {
      staggerChildren: 0.02,
      staggerDirection: -1,
    },
  },
};

/** Tighter stagger — for dense rows (table rows, ranked opportunities). */
export const staggerTight: Variants = {
  hidden: { opacity: 1 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.025,
      delayChildren:   0.03,
    },
  },
};

/** Top-bar/sidebar mount — single shot, no children. */
export const chromeIn: Variants = {
  hidden: { opacity: 0, y: -4 },
  show:   { opacity: 1, y: 0, transition: { duration: 0.4, ease: easeEnter } },
};

/** Tap feedback — used on Push / Drill buttons. */
export const tapShrink = {
  whileTap: { scale: 0.97 },
  whileHover: { y: -1 },
  transition: { duration: 0.16, ease: easeStandard },
};
