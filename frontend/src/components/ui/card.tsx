import * as React from "react";
import { cn } from "@/lib/utils";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "relative rounded-2xl border border-border bg-gradient-to-b from-[rgba(42,33,18,.6)] to-[rgba(16,12,7,.9)] p-5 shadow-[inset_0_0_0_1px_rgba(230,195,92,.07),0_20px_44px_-26px_rgba(0,0,0,.95)]",
        "before:pointer-events-none before:absolute before:inset-1 before:rounded-xl before:border before:border-gold/15",
        className
      )}
      {...props}
    />
  )
);
Card.displayName = "Card";

const CardTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("relative z-10 text-base font-bold text-gold-bright", className)} {...props} />
  )
);
CardTitle.displayName = "CardTitle";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("relative z-10 text-sm text-muted-foreground", className)} {...props} />
  )
);
CardContent.displayName = "CardContent";

export { Card, CardTitle, CardContent };
