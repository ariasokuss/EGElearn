"use client";

import { memo } from "react";
import { motion } from "motion/react";

const TOOLTIP_TRANSITION = { duration: 0.15, ease: "easeOut" as const };

type ScrollerTooltipProps = {
  title: string;
  description: string;
  style: React.CSSProperties;
};

function ScrollerTooltipInner({ title, description, style }: ScrollerTooltipProps) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 8, scale: 0.96 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 8, scale: 0.96 }}
      transition={TOOLTIP_TRANSITION}
      className="absolute right-[calc(100%+12px)] w-[240px] rounded-2xl border border-[#FCFCFC14] bg-[#242529] p-4"
      style={style}
    >
      <p className="truncate nova-text-label-medium text-white">{title}</p>
      {description && (
        <p className="mt-1 line-clamp-2 nova-text-label-tiny text-[#FCFCFC99]">
          {description}
        </p>
      )}
    </motion.div>
  );
}

export const ScrollerTooltip = memo(ScrollerTooltipInner);
