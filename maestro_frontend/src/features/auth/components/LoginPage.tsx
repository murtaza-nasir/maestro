import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store'
import { useTheme } from '../../../contexts/ThemeContext'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'
import { Checkbox } from '../../../components/ui/checkbox'
import { Eye, EyeOff, Lock, User } from 'lucide-react'
import AnimatedBackground from '../../../components/ui/AnimatedBackground'

export const LoginPage: React.FC = () => {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  
  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()
  const { theme } = useTheme()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    try {
      await login(username, password, rememberMe)
      navigate('/dashboard')
    } catch (error: any) {
      let errorMessage = t('login.loginFailed')
      
      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map((err: any) => err.msg || err).join(', ')
        } else {
          errorMessage = t('login.invalidCredentials')
        }
      }
      
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-purple-50/30 to-blue-50/20 dark:from-slate-900 dark:via-purple-950/20 dark:to-blue-950/10 py-12 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
      <AnimatedBackground />

      <div className="max-w-md w-full space-y-8 relative z-10">
        {/* Logo and Header */}
        <div className="text-center">
          <div className="flex justify-center mb-6">
            <div className="relative group">
              <img 
                src={theme === 'dark' ? '/icon_dark.png' : '/icon_original.png'} 
                alt="MAESTRO Logo" 
                className="h-16 w-16 transition-transform hover:scale-105 drop-shadow-sm"
              />
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 to-blue-500/10 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 -z-10"></div>
            </div>
          </div>
          
          <div className="space-y-2">
            <h1 className="text-3xl font-bold text-foreground tracking-tight">
              {t('login.title')}
            </h1>
            <p className="text-muted-foreground">
              {t('login.subtitle')}
            </p>
          </div>
        </div>
        
        {/* Login Card */}
        <Card className="border-border/50 bg-card/80 backdrop-blur-sm shadow-xl">
          <CardHeader className="space-y-1 pb-6">
            <CardTitle className="text-xl font-semibold text-center">
              {t('login.signIn')}
            </CardTitle>
            <CardDescription className="text-center">
              {t('login.signInSubtext')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}
              
              {/* Username Field */}
              <div className="space-y-2">
                <label htmlFor="username" className="block text-sm font-medium text-foreground">
                  {t('login.username')}
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="username"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    className="pl-10 h-11 bg-background/50 border-border/50 focus:border-primary/50 focus:ring-primary/20"
                    placeholder={t('login.usernamePlaceholder')}
                  />
                </div>
              </div>
              
              {/* Password Field */}
              <div className="space-y-2">
                <label htmlFor="password" className="block text-sm font-medium text-foreground">
                  {t('login.password')}
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="pl-10 pr-10 h-11 bg-background/50 border-border/50 focus:border-primary/50 focus:ring-primary/20"
                    placeholder={t('login.passwordPlaceholder')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* Remember Me */}
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="remember-me"
                  checked={rememberMe}
                  onCheckedChange={(checked: boolean) => setRememberMe(checked)}
                />
                <label
                  htmlFor="remember-me"
                  className="text-sm text-muted-foreground cursor-pointer select-none"
                >
                  {t('login.rememberMe')}
                </label>
              </div>
              
              {/* Submit Button */}
              <Button
                type="submit"
                disabled={isLoading}
                className="w-full h-11 bg-gradient-to-r from-primary/90 to-primary text-primary-foreground font-medium transition-all duration-200 shadow-lg hover:shadow-xl border-0 hover:from-primary hover:to-primary/90"
              >
                {isLoading ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin"></div>
                    {t('login.signingIn')}
                  </div>
                ) : (
                  t('login.signIn')
                )}
              </Button>
            </form>
            
            {/* Register Link */}
            <div className="mt-6 text-center">
              <p className="text-sm text-muted-foreground">
                {t('login.noAccount')}{' '}
                <Link 
                  to="/register" 
                  className="font-medium text-primary hover:text-primary/80 transition-colors"
                >
                  {t('login.signUp')}
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

    </div>
  )
}
