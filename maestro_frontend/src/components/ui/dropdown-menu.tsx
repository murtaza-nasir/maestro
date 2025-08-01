import React, { useState, useRef, useEffect } from 'react'

interface DropdownMenuProps {
  children: React.ReactNode
}

interface DropdownMenuTriggerProps {
  asChild?: boolean
  children: React.ReactNode
}

interface DropdownMenuContentProps {
  align?: 'start' | 'center' | 'end'
  className?: string
  children: React.ReactNode
}

interface DropdownMenuItemProps {
  onClick?: (e: React.MouseEvent) => void
  className?: string
  children: React.ReactNode
}

// Context for sharing state between components
const DropdownContext = React.createContext<{
  isOpen: boolean
  setIsOpen: (open: boolean) => void
}>({
  isOpen: false,
  setIsOpen: () => {}
})

export const DropdownMenu: React.FC<DropdownMenuProps> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  return (
    <DropdownContext.Provider value={{ isOpen, setIsOpen }}>
      <div ref={containerRef} className="relative">
        {children}
      </div>
    </DropdownContext.Provider>
  )
}

export const DropdownMenuTrigger: React.FC<DropdownMenuTriggerProps> = ({ 
  asChild, 
  children
}) => {
  const { isOpen, setIsOpen } = React.useContext(DropdownContext)

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    console.log('DropdownMenuTrigger clicked, current isOpen:', isOpen)
    setIsOpen(!isOpen)
  }

  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children, {
      onClick: handleClick
    } as any)
  }

  return (
    <button onClick={handleClick}>
      {children}
    </button>
  )
}

export const DropdownMenuContent: React.FC<DropdownMenuContentProps> = ({ 
  align = 'start',
  className = '',
  children
}) => {
  const { isOpen } = React.useContext(DropdownContext)

  if (!isOpen) return null

  return (
    <div
      className={`absolute top-full mt-1 min-w-[12rem] overflow-hidden rounded-md border border-gray-200 bg-white p-1 text-gray-950 shadow-md z-50 whitespace-nowrap ${
        align === 'end' ? 'right-0' : align === 'center' ? 'left-1/2 transform -translate-x-1/2' : 'left-0'
      } ${className}`}
    >
      {children}
    </div>
  )
}

export const DropdownMenuItem: React.FC<DropdownMenuItemProps> = ({ 
  onClick,
  className = '',
  children
}) => {
  const { setIsOpen } = React.useContext(DropdownContext)

  const handleClick = (e: React.MouseEvent) => {
    console.log('DropdownMenuItem clicked!', children)
    e.stopPropagation()
    
    // Execute the onClick handler first
    if (onClick) {
      console.log('Executing onClick handler...')
      onClick(e)
    }
    
    // Then close the dropdown
    console.log('Closing dropdown...')
    setIsOpen(false)
  }

  return (
    <div
      className={`relative flex cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-gray-100 focus:bg-gray-100 ${className}`}
      onClick={handleClick}
    >
      {children}
    </div>
  )
}
