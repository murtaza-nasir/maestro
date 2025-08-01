import React from 'react';
import { Check } from 'lucide-react';
import { cn } from '../lib/utils';
import type { ColorScheme } from '../contexts/ThemeContext';

interface ColorSchemeOption {
  value: ColorScheme;
  name: string;
  lightColor: string;
  darkColor: string;
}

const colorSchemes: ColorSchemeOption[] = [
  { value: 'default', name: 'Black & White', lightColor: '#000000', darkColor: '#ffffff' },
  { value: 'blue', name: 'Blue', lightColor: '#3b82f6', darkColor: '#8b5cf6' },
  { value: 'emerald', name: 'Emerald', lightColor: '#10b981', darkColor: '#6ee7b7' },
  { value: 'purple', name: 'Purple', lightColor: '#8b5cf6', darkColor: '#c4b5fd' },
  { value: 'rose', name: 'Rose', lightColor: '#f43f5e', darkColor: '#fda4af' },
  { value: 'amber', name: 'Amber', lightColor: '#f59e0b', darkColor: '#fbbf24' },
  { value: 'teal', name: 'Teal', lightColor: '#14b8a6', darkColor: '#5eead4' },
];

interface ColorSchemeSelectorProps {
  selectedScheme: ColorScheme;
  onSchemeChange: (scheme: ColorScheme) => void;
}

export const ColorSchemeSelector: React.FC<ColorSchemeSelectorProps> = ({
  selectedScheme,
  onSchemeChange,
}) => {
  return (
    <div className="flex flex-wrap gap-3">
      {colorSchemes.map((scheme) => (
        <button
          key={scheme.value}
          type="button"
          onClick={() => onSchemeChange(scheme.value)}
          className={cn(
            'relative h-10 w-10 rounded-full border-2 flex items-center justify-center transition-all',
            selectedScheme === scheme.value
              ? 'border-primary'
              : 'border-transparent hover:border-muted-foreground/50'
          )}
          title={scheme.name}
        >
          <div className="flex -space-x-1.5">
            <div
              className="h-5 w-5 rounded-full border border-border/50"
              style={{ backgroundColor: scheme.lightColor }}
            />
            <div
              className="h-5 w-5 rounded-full border border-border/50"
              style={{ backgroundColor: scheme.darkColor }}
            />
          </div>
          {selectedScheme === scheme.value && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="bg-background/90 rounded-full p-1">
                <Check className="h-3 w-3 text-foreground" />
              </div>
            </div>
          )}
        </button>
      ))}
    </div>
  );
};
