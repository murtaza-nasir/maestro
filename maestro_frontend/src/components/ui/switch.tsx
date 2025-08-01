import * as React from "react"
import { cn } from "../../lib/utils"

export interface SwitchProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ className, checked, onCheckedChange, ...props }, ref) => {
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      e.preventDefault()
      const newChecked = !checked
      onCheckedChange?.(newChecked)
    }

    return (
      <button
        type="button"
        className={cn(
          "relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          checked ? "bg-blue-600" : "bg-gray-200",
          className
        )}
        ref={ref}
        role="switch"
        aria-checked={checked}
        onClick={handleClick}
        {...props}
      >
        <span
          className={cn(
            "pointer-events-none block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform",
            checked ? "translate-x-6" : "translate-x-1"
          )}
        />
      </button>
    )
  }
)
Switch.displayName = "Switch"

export { Switch }
