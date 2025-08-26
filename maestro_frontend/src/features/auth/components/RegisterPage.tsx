import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../store'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../../components/ui/card'

export const RegisterPage: React.FC = () => {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  
  const register = useAuthStore((state) => state.register)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsLoading(true)
    setError('')

    if (password !== confirmPassword) {
      setError(t('register.passwordsDoNotMatch'))
      setIsLoading(false)
      return
    }

    if (password.length < 6) {
      setError(t('register.passwordTooShort'))
      setIsLoading(false)
      return
    }

    try {
      await register(username, password)
      navigate('/dashboard')
    } catch (error: any) {
      let errorMessage = t('register.registrationFailed')
      
      if (error.response?.data?.detail) {
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail
        } else if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map((err: any) => err.msg || err).join(', ')
        } else {
          errorMessage = t('register.invalidInput')
        }
      }
      
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900">{t('register.title')}</h1>
          <p className="mt-2 text-sm text-gray-600">{t('register.subtitle')}</p>
        </div>
        
        <Card>
          <CardHeader>
            <CardTitle>{t('register.createAccount')}</CardTitle>
            <CardDescription>
              {t('register.createAccountSubtext')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
                  {error}
                </div>
              )}
              
              <div>
                <label htmlFor="username" className="block text-sm font-medium text-gray-700">
                  {t('register.username')}
                </label>
                <Input
                  id="username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="mt-1"
                  placeholder={t('register.usernamePlaceholder')}
                />
              </div>
              
              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                  {t('register.password')}
                </label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="mt-1"
                  placeholder={t('register.passwordPlaceholder')}
                />
              </div>
              
              <div>
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
                  {t('register.confirmPassword')}
                </label>
                <Input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className="mt-1"
                  placeholder={t('register.confirmPasswordPlaceholder')}
                />
              </div>
              
              <Button
                type="submit"
                disabled={isLoading}
                className="w-full"
              >
                {isLoading ? t('register.creatingAccount') : t('register.createAccount')}
              </Button>
            </form>
            
            <div className="mt-4 text-center">
              <p className="text-sm text-gray-600">
                {t('register.alreadyHaveAccount')}{' '}
                <Link to="/login" className="font-medium text-blue-600 hover:text-blue-500">
                  {t('register.signIn')}
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
