import * as React from "react"
import { Check } from "lucide-react"
import { cn } from "../../lib/utils"

interface CheckboxProps {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  disabled?: boolean
  id?: string
  className?: string
}

const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(
  ({ className, checked = false, onCheckedChange, disabled = false, id, ...props }, ref) => {
    const handleClick = () => {
      if (!disabled && onCheckedChange) {
        onCheckedChange(!checked)
      }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault()
        handleClick()
      }
    }

    return (
      <button
        ref={ref}
        type="button"
        role="checkbox"
        aria-checked={checked}
        id={id}
        disabled={disabled}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className={cn(
          "peer h-4 w-4 shrink-0 rounded-sm border border-primary ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-colors",
          checked && "bg-primary text-primary-foreground border-primary",
          !checked && "bg-background hover:bg-accent",
          className
        )}
        {...props}
      >
        {checked && (
          <Check className="h-3 w-3 text-current" />
        )}
      </button>
    )
  }
)

Checkbox.displayName = "Checkbox"

export { Checkbox }
