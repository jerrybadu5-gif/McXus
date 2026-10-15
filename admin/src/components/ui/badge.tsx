import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badge = cva("inline-flex items-center rounded-md px-1.5 py-0.5 text-2xs font-semibold", {
  variants: {
    tone: {
      plain: "bg-tint text-body",
      gold: "bg-gold-soft text-gold-ink",
      late: "bg-late-soft text-late",
      ok: "bg-ok-soft text-ok",
      navy: "bg-navy text-white",
    },
  },
  defaultVariants: { tone: "plain" },
});

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}
