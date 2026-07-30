import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-bold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "text-white bg-gradient-to-b from-ember to-ember-deep shadow-[0_0_0_1px_rgba(255,190,130,.38),0_10px_26px_-12px_rgba(192,57,43,.75),inset_0_1px_0_rgba(255,255,255,.26)] hover:-translate-y-px",
        gold:
          "text-[#140f08] bg-gradient-to-b from-gold-bright to-gold-deep shadow-[0_8px_22px_-12px_rgba(230,195,92,.7)] hover:-translate-y-px",
        outline:
          "border border-gold/40 text-gold bg-[rgba(22,18,11,.7)] hover:bg-[rgba(34,28,17,.85)]",
        ghost: "text-muted-foreground hover:bg-secondary",
      },
      size: {
        default: "h-11 px-5 py-2",
        sm: "h-9 px-4",
        lg: "h-12 px-7 text-base",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />
  )
);
Button.displayName = "Button";

export { Button, buttonVariants };
