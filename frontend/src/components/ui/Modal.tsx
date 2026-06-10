import { ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import clsx from 'clsx';
import { X } from 'lucide-react';

type Props = {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
};

const SIZE: Record<NonNullable<Props['size']>, string> = {
  sm: 'max-w-md',
  md: 'max-w-xl',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
};

const EASE_ENTER: [number, number, number, number] = [0.16, 1, 0.3, 1];
const EASE_EXIT:  [number, number, number, number] = [0.4, 0, 1, 1];

export function Modal({ open, onClose, title, subtitle, right, children, size = 'lg' }: Props) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [open, onClose]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          key="modal-root"
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.22, ease: EASE_ENTER }}
        >
          {/* backdrop */}
          <motion.div
            className="absolute inset-0 bg-bg/85 backdrop-blur-md"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease: EASE_ENTER }}
          />

          {/* dialog */}
          <motion.div
            className={clsx(
              'relative w-full bg-bg-surface border border-border rounded-lg shadow-2xl flex flex-col max-h-[90vh]',
              SIZE[size],
            )}
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 6, transition: { duration: 0.16, ease: EASE_EXIT } }}
            transition={{ duration: 0.3, ease: EASE_ENTER }}
          >
            {/* gold accent stripe */}
            <div
              aria-hidden
              className="absolute inset-x-4 top-0 h-px pointer-events-none"
              style={{ background: 'linear-gradient(90deg, transparent, rgba(212,175,55,0.6), transparent)' }}
            />

            {/* header */}
            {(title || right) && (
              <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-border/70">
                <div className="flex-1 min-w-0">
                  {title && (
                    <div className="font-display font-bold tracking-[0.2em] text-sm text-text-primary uppercase">
                      {title}
                    </div>
                  )}
                  {subtitle && (
                    <div className="text-[11px] font-mono text-text-tertiary mt-0.5 tabular">
                      {subtitle}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {right}
                  <motion.button
                    onClick={onClose}
                    whileHover={{ scale: 1.1, rotate: 90 }}
                    whileTap={{ scale: 0.92 }}
                    transition={{ duration: 0.2, ease: EASE_ENTER }}
                    className="p-1.5 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
                    aria-label="Close"
                  >
                    <X className="w-4 h-4" />
                  </motion.button>
                </div>
              </div>
            )}

            {/* body */}
            <div className="flex-1 overflow-y-auto p-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
