import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { LoginPage, RegisterPage, PrivateRoute } from './features/auth/components'
import { MainLayout } from './components/layout'
import { UnifiedLayout } from './components/layout/UnifiedLayout'
import { Dashboard } from './pages/Dashboard'
import { useAuthStore } from './features/auth/store'
import { ToastProvider } from './components/ui/toast'
import { DocumentProvider } from './features/documents/context/DocumentContext'
import { DocumentUploadProvider } from './features/documents/context/DocumentUploadContext'
import { clearOldStorageData, logStorageUsage, initHybridStorage } from './utils/storageUtils'
import { ThemeProvider } from './contexts/ThemeContext'

function App() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  // Initialize storage system on app start
  useEffect(() => {
    const initStorage = async () => {
      try {
        // Initialize hybrid storage (IndexedDB + localStorage)
        await initHybridStorage()
        
        // Clear old storage data if quota is exceeded
        clearOldStorageData()
        
        // Log current storage usage in development
        if (import.meta.env.DEV) {
          logStorageUsage()
        }
      } catch (error) {
        console.error('Failed to initialize storage system:', error)
      }
    }
    
    initStorage()
  }, [])

  return (
    <ThemeProvider>
      <ToastProvider>
        <Router>
          <div className="App">
          <Routes>
          {/* Public routes */}
          <Route 
            path="/login" 
            element={
              isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />
            } 
          />
          <Route 
            path="/register" 
            element={
              isAuthenticated ? <Navigate to="/dashboard" replace /> : <RegisterPage />
            } 
          />
          
          {/* Protected routes */}
          <Route 
            path="/*" 
            element={
              <PrivateRoute>
                <DocumentProvider>
                  <DocumentUploadProvider>
                    <MainLayout />
                  </DocumentUploadProvider>
                </DocumentProvider>
              </PrivateRoute>
            } 
          >
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="app" element={<UnifiedLayout />} />
            <Route path="chat" element={<Navigate to="/app" replace />} />
            <Route path="chat/:chatId" element={<Navigate to="/app" replace />} />
            <Route path="documents" element={<Navigate to="/app" replace />} />
            <Route path="" element={<Navigate to="dashboard" replace />} />
          </Route>
          
          {/* Default redirect */}
          <Route 
            path="/" 
            element={
              <Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />
            } 
          />
          
          {/* Catch all route */}
          <Route 
            path="*" 
            element={
              <Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />
            } 
          />
          </Routes>
          </div>
        </Router>
      </ToastProvider>
    </ThemeProvider>
  )
}

export default App
