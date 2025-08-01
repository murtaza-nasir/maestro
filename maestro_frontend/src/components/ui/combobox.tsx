import React, { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './button'
import { Input } from './input'
import { Card } from './card'
import { ChevronDown, Check } from 'lucide-react'

interface ComboboxProps {
  value: string
  onValueChange: (value: string) => void
  options: string[]
  placeholder?: string
  className?: string
}

export const Combobox: React.FC<ComboboxProps> = ({
  value,
  onValueChange,
  options,
  placeholder = "Select option...",
  className = ""
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [dropdownPosition, setDropdownPosition] = useState({ top: 0, left: 0, width: 0 })
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const filteredOptions = options.filter(option =>
    option.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const updateDropdownPosition = () => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      const dropdownHeight = 300 // Approximate max height (60 * 4 + padding)
      const viewportHeight = window.innerHeight
      const spaceBelow = viewportHeight - rect.bottom
      const spaceAbove = rect.top
      
      // Determine if dropdown should appear above or below
      const shouldShowAbove = spaceBelow < dropdownHeight && spaceAbove > spaceBelow
      
      let top: number
      if (shouldShowAbove) {
        top = rect.top + window.scrollY - dropdownHeight - 4
      } else {
        top = rect.bottom + window.scrollY + 4
      }
      
      // Ensure dropdown doesn't go off-screen horizontally
      let left = rect.left + window.scrollX
      const dropdownWidth = rect.width
      if (left + dropdownWidth > window.innerWidth) {
        left = window.innerWidth - dropdownWidth - 8
      }
      if (left < 8) {
        left = 8
      }
      
      setDropdownPosition({
        top,
        left,
        width: rect.width
      })
    }
  }

  useEffect(() => {
    if (isOpen) {
      updateDropdownPosition()
    }
  }, [isOpen])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
        setSearchTerm('')
        setHighlightedIndex(-1)
      }
    }

    const handleScroll = () => {
      if (isOpen) {
        updateDropdownPosition()
      }
    }

    const handleResize = () => {
      if (isOpen) {
        updateDropdownPosition()
      }
    }

    // Use a timeout to allow click events to process before checking for outside clicks
    if (isOpen) {
      const timeoutId = setTimeout(() => {
        document.addEventListener('click', handleClickOutside)
      }, 0)
      
      window.addEventListener('scroll', handleScroll, true)
      window.addEventListener('resize', handleResize)
      
      return () => {
        clearTimeout(timeoutId)
        document.removeEventListener('click', handleClickOutside)
        window.removeEventListener('scroll', handleScroll, true)
        window.removeEventListener('resize', handleResize)
      }
    }
  }, [isOpen])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'Enter' || e.key === 'ArrowDown') {
        setIsOpen(true)
        setHighlightedIndex(0)
        e.preventDefault()
      }
      return
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightedIndex(prev => 
          prev < filteredOptions.length - 1 ? prev + 1 : 0
        )
        break
      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex(prev => 
          prev > 0 ? prev - 1 : filteredOptions.length - 1
        )
        break
      case 'Enter':
        e.preventDefault()
        if (highlightedIndex >= 0 && highlightedIndex < filteredOptions.length) {
          onValueChange(filteredOptions[highlightedIndex])
          setIsOpen(false)
          setSearchTerm('')
          setHighlightedIndex(-1)
        }
        break
      case 'Escape':
        setIsOpen(false)
        setSearchTerm('')
        setHighlightedIndex(-1)
        break
    }
  }

  const handleOptionClick = (option: string) => {
    onValueChange(option)
    setIsOpen(false)
    setSearchTerm('')
    setHighlightedIndex(-1)
  }

  const displayValue = value || placeholder

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <Button
        type="button"
        variant="outline"
        className="w-full justify-between text-left font-normal"
        onClick={() => {
          setIsOpen(!isOpen)
          if (!isOpen) {
            setTimeout(() => inputRef.current?.focus(), 0)
          }
        }}
      >
        <span className={value ? "text-foreground" : "text-muted-foreground"}>
          {displayValue}
        </span>
        <ChevronDown className="h-4 w-4 opacity-50" />
      </Button>

      {isOpen && createPortal(
        <Card className="fixed z-[9999] p-0 shadow-lg border" style={{
          width: dropdownPosition.width,
          top: dropdownPosition.top,
          left: dropdownPosition.left
        }}>
          <div className="p-2">
            <Input
              ref={inputRef}
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value)
                setHighlightedIndex(-1)
              }}
              onKeyDown={handleKeyDown}
              placeholder="Search models..."
              className="w-full"
            />
          </div>
          <div className="max-h-60 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className="p-2 text-sm text-muted-foreground">
                No models found
              </div>
            ) : (
              filteredOptions.map((option, index) => (
                <div
                  key={option}
                  className={`
                    px-2 py-1.5 text-sm cursor-pointer flex items-center justify-between
                    ${index === highlightedIndex ? 'bg-accent' : ''}
                    ${option === value ? 'bg-accent/50' : ''}
                    hover:bg-accent
                  `}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    handleOptionClick(option)
                  }}
                  onMouseEnter={() => setHighlightedIndex(index)}
                >
                  <span>{option}</span>
                  {option === value && <Check className="h-4 w-4" />}
                </div>
              ))
            )}
          </div>
        </Card>,
        document.body
      )}
    </div>
  )
}
