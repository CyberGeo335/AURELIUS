import { useEffect } from 'react';
import { motion, useReducedMotion, useSpring, useTransform } from 'motion/react';
import { money } from '../../domain/finance';

export function AnimatedMoney({ value }: { value: number }) {
  const reduced = useReducedMotion();
  const spring = useSpring(0, { stiffness: 170, damping: 27 });
  const formatted = useTransform(spring, (current) => money(current));
  useEffect(() => {
    if (reduced) spring.jump(value);
    else spring.set(value);
  }, [reduced, spring, value]);
  return (
    <span>
      <span className="sr-only">{money(value)}</span>
      <motion.span aria-hidden>{formatted}</motion.span>
    </span>
  );
}
