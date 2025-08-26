import React from 'react'
import { useTranslation } from 'react-i18next'
import { useTheme } from '../../../contexts/ThemeContext'
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import { Label } from '../../../components/ui/label'
import { Switch } from '../../../components/ui/switch'
import { ColorSchemeSelector } from '../../../components/ColorSchemeSelector'
import type { ColorScheme } from '../../../contexts/ThemeContext'

export const AppearanceSettingsTab: React.FC = () => {
  const { t } = useTranslation()
  const { theme, setTheme, colorScheme, setColorScheme } = useTheme()

  const handleThemeChange = (isDarkMode: boolean) => {
    try {
      const newTheme = isDarkMode ? 'dark' : 'light'
      setTheme(newTheme)
    } catch (error) {
      console.error('Error changing theme:', error)
    }
  }

  const handleColorSchemeChange = (scheme: ColorScheme) => {
    try {
      setColorScheme(scheme)
    } catch (error) {
      console.error('Error changing color scheme:', error)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('appearanceSettings.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between">
            <Label htmlFor="dark-mode-toggle">{t('appearanceSettings.darkMode')}</Label>
            <Switch
              id="dark-mode-toggle"
              checked={theme === 'dark'}
              onCheckedChange={handleThemeChange}
            />
          </div>
          <div className="space-y-2">
            <Label>{t('appearanceSettings.colorScheme')}</Label>
            <ColorSchemeSelector
              selectedScheme={colorScheme}
              onSchemeChange={handleColorSchemeChange}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
