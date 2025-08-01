import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useViewStore } from '../stores/viewStore'
import { useTheme } from '../contexts/ThemeContext'
import { apiClient } from '../config/api'
// import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { 
  Search, 
  PenTool, 
  FolderOpen,
  ArrowRight,
  BarChart3,
  Clock,
  CheckCircle,
  PlayCircle,
  Activity
} from 'lucide-react'

interface DashboardStats {
  total_chats: number
  total_documents: number
  total_writing_sessions: number
  total_missions: number
  recent_activity: string
  research_sessions: number
  writing_sessions: number
  completed_missions: number
  active_missions: number
}

export const Dashboard: React.FC = () => {
  const navigate = useNavigate()
  const { setView } = useViewStore()
  const { theme } = useTheme()
  const [stats, setStats] = useState<DashboardStats>({
    total_chats: 0,
    total_documents: 0,
    total_writing_sessions: 0,
    total_missions: 0,
    recent_activity: 'No recent activity',
    research_sessions: 0,
    writing_sessions: 0,
    completed_missions: 0,
    active_missions: 0
  })

  // Fetch dashboard stats
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await apiClient.get('/api/dashboard/stats')
        setStats(response.data)
      } catch (error) {
        console.error('Failed to fetch dashboard stats:', error)
        // Keep default values on error
      }
    }

    fetchStats()
  }, [])

  const handleStartResearch = () => {
    setView('research')
    navigate('/app')
  }

  const handleStartWriting = () => {
    setView('writing')
    navigate('/app')
  }

  const handleManageDocuments = () => {
    setView('documents')
    navigate('/app')
  }

  const actionCards = [
    {
      title: 'Start Research',
      description: 'Begin a new AI-powered research project',
      icon: Search,
      action: handleStartResearch,
      stats: `${stats.research_sessions} research sessions`,
      gradient: 'from-blue-500/10 to-cyan-500/10',
      iconColor: 'text-blue-600 dark:text-blue-400',
      borderColor: 'border-blue-200/50 dark:border-blue-800/50'
    },
    {
      title: 'Start Writing',
      description: 'Create and edit documents with AI assistance',
      icon: PenTool,
      action: handleStartWriting,
      stats: `${stats.writing_sessions} writing sessions`,
      gradient: 'from-purple-500/10 to-pink-500/10',
      iconColor: 'text-purple-600 dark:text-purple-400',
      borderColor: 'border-purple-200/50 dark:border-purple-800/50'
    },
    {
      title: 'Manage Documents',
      description: 'Organize and access your research materials',
      icon: FolderOpen,
      action: handleManageDocuments,
      stats: `${stats.total_documents} documents`,
      gradient: 'from-emerald-500/10 to-teal-500/10',
      iconColor: 'text-emerald-600 dark:text-emerald-400',
      borderColor: 'border-emerald-200/50 dark:border-emerald-800/50'
    }
  ]

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-6 py-12">
        {/* Header Section */}
        <div className="text-center mb-16">
          <div className="flex justify-center mb-6">
            <div className="relative">
              <img 
                src={theme === 'dark' ? '/icon_dark.png' : '/icon_original.png'} 
                alt="MAESTRO Logo" 
                className="h-16 w-16 transition-transform hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-r from-blue-500/20 to-purple-500/20 rounded-full blur-xl -z-10"></div>
            </div>
          </div>
          
          <h1 className="text-4xl font-bold text-foreground mb-4 tracking-tight">
            MAESTRO
          </h1>
          
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
            Your intelligent research and writing companion.
          </p>
          
          {stats.recent_activity !== 'No recent activity' && (
            <div className="flex items-center justify-center mt-6 text-sm text-muted-foreground">
              <Clock className="h-4 w-4 mr-2" />
              Last activity: {stats.recent_activity}
            </div>
          )}
        </div>

        {/* Action Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          {actionCards.map((card, index) => {
            const Icon = card.icon
            return (
              <Card 
                key={index}
                className={`group relative overflow-hidden border ${card.borderColor} bg-gradient-to-br ${card.gradient} hover:shadow-lg transition-all duration-300 cursor-pointer`}
                onClick={card.action}
              >
                <CardHeader className="pb-4">
                  <div className="flex items-center justify-between">
                    <div className={`p-3 rounded-xl bg-background/50 ${card.iconColor}`}>
                      <Icon className="h-6 w-6" />
                    </div>
                    <ArrowRight className="h-5 w-5 text-muted-foreground group-hover:translate-x-1 transition-transform" />
                  </div>
                  <CardTitle className="text-xl font-semibold text-foreground">
                    {card.title}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-muted-foreground mb-4 leading-relaxed">
                    {card.description}
                  </p>
                  <div className="flex items-center text-sm text-muted-foreground">
                    <BarChart3 className="h-4 w-4 mr-2" />
                    {card.stats}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>

        {/* Comprehensive Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {/* Total Sessions */}
          <Card className="border-blue-200/50 dark:border-blue-800/50 bg-gradient-to-br from-blue-500/5 to-cyan-500/5">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Sessions</p>
                  <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {stats.total_chats}
                  </p>
                </div>
                <div className="p-3 rounded-full bg-blue-100 dark:bg-blue-900/30">
                  <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                </div>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                Research + Writing combined
              </div>
            </CardContent>
          </Card>

          {/* Mission Progress */}
          <Card className="border-green-200/50 dark:border-green-800/50 bg-gradient-to-br from-green-500/5 to-emerald-500/5">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Missions</p>
                  <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                    {stats.completed_missions}/{stats.total_missions}
                  </p>
                </div>
                <div className="p-3 rounded-full bg-green-100 dark:bg-green-900/30">
                  <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
                </div>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {stats.total_missions > 0 ? 
                  `${Math.round((stats.completed_missions / stats.total_missions) * 100)}% completion rate` : 
                  'No missions yet'
                }
              </div>
            </CardContent>
          </Card>

          {/* Active Work */}
          <Card className="border-orange-200/50 dark:border-orange-800/50 bg-gradient-to-br from-orange-500/5 to-amber-500/5">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Active Missions</p>
                  <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">
                    {stats.active_missions}
                  </p>
                </div>
                <div className="p-3 rounded-full bg-orange-100 dark:bg-orange-900/30">
                  <PlayCircle className="h-5 w-5 text-orange-600 dark:text-orange-400" />
                </div>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {stats.active_missions > 0 ? 'Currently in progress' : 'No active work'}
              </div>
            </CardContent>
          </Card>

          {/* Session Mix */}
          <Card className="border-purple-200/50 dark:border-purple-800/50 bg-gradient-to-br from-purple-500/5 to-pink-500/5">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Session Mix</p>
                  <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                    {stats.total_chats > 0 ? Math.round((stats.research_sessions / stats.total_chats) * 100) : 0}%
                  </p>
                </div>
                <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900/30">
                  <BarChart3 className="h-5 w-5 text-purple-600 dark:text-purple-400" />
                </div>
              </div>
              
              {/* Stacked Bar Chart */}
              <div className="space-y-3">
                <div className="flex w-full h-3 bg-muted rounded-full overflow-hidden">
                  <div 
                    className="bg-blue-500 transition-all duration-500"
                    style={{ 
                      width: stats.total_chats > 0 ? 
                        `${(stats.research_sessions / stats.total_chats) * 100}%` : 
                        '0%' 
                    }}
                  ></div>
                  <div 
                    className="bg-purple-500 transition-all duration-500"
                    style={{ 
                      width: stats.total_chats > 0 ? 
                        `${(stats.writing_sessions / stats.total_chats) * 100}%` : 
                        '0%' 
                    }}
                  ></div>
                </div>
                
                <div className="flex justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                    <span>Research {stats.total_chats > 0 ? Math.round((stats.research_sessions / stats.total_chats) * 100) : 0}%</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                    <span>Writing {stats.total_chats > 0 ? Math.round((stats.writing_sessions / stats.total_chats) * 100) : 0}%</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

      </div>
    </div>
  )
}
