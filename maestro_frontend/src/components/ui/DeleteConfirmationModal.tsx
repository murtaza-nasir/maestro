import React from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Trash2, X } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './dialog'
import { Button } from './button'

interface DeleteConfirmationModalProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  description: string
  itemName?: string
  itemType?: 'chat' | 'document' | 'session' | 'item'
  isLoading?: boolean
  variant?: 'single' | 'bulk'
  count?: number
}

export const DeleteConfirmationModal: React.FC<DeleteConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  itemName,
  itemType = 'item',
  isLoading = false,
  variant = 'single',
  count = 1
}) => {
  const { t } = useTranslation()

  const getIcon = () => {
    switch (itemType) {
      case 'chat':
      case 'session':
        return <Trash2 className="h-5 w-5" />
      case 'document':
        return <Trash2 className="h-5 w-5" />
      default:
        return <Trash2 className="h-5 w-5" />
    }
  }

  const getWarningText = () => {
    return t(`deleteConfirmation.permanentDeleteWarning`, { count, itemType, nsSeparator: false, defaultValue: `This will permanently delete this ${itemType}.` })
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md bg-background border border-border shadow-lg">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-6 top-6 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none text-muted-foreground hover:text-foreground"
          disabled={isLoading}
        >
          <X className="h-4 w-4" />
          <span className="sr-only">{t('deleteConfirmation.close')}</span>
        </button>

        {/* Header with proper padding */}
        <DialogHeader className="pb-6 pt-6 px-6">
          <div className="flex items-center gap-4 mb-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive border border-destructive/20">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="flex-1">
              <DialogTitle className="text-left text-xl font-semibold text-foreground leading-tight">
                {title}
              </DialogTitle>
            </div>
          </div>
        </DialogHeader>

        {/* Content with proper padding */}
        <div className="px-6 pb-6 space-y-5">
          {/* Main description */}
          <p className="text-sm text-muted-foreground leading-relaxed">
            {description}
          </p>

          {/* Item name if provided */}
          {itemName && (
            <div className="rounded-lg bg-muted/30 p-4 border border-border/50">
              <div className="flex items-center gap-3 text-sm">
                <div className="text-muted-foreground">
                  {getIcon()}
                </div>
                <span className="font-medium text-foreground truncate">
                  {itemName}
                </span>
              </div>
            </div>
          )}

          {/* Warning section */}
          <div className="rounded-lg bg-destructive/5 border border-destructive/20 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-destructive mt-0.5 flex-shrink-0" />
              <div className="space-y-2">
                <p className="text-sm font-semibold text-destructive">
                  {t('deleteConfirmation.warning')}
                </p>
                <p className="text-xs text-destructive/80 leading-relaxed">
                  {getWarningText()}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer with proper padding */}
        <DialogFooter className="px-6 pb-6 pt-2">
          <div className="flex gap-3 w-full sm:w-auto sm:justify-end">
            <Button
              variant="outline"
              onClick={onClose}
              disabled={isLoading}
              className="flex-1 sm:flex-none h-10 px-6 text-sm font-medium border-border hover:bg-muted/50 hover:text-foreground"
            >
              {t('deleteConfirmation.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={onConfirm}
              disabled={isLoading}
              className="flex-1 sm:flex-none h-10 px-6 text-sm font-medium bg-destructive hover:bg-destructive/90 text-destructive-foreground"
            >
              {isLoading ? (
                <div className="flex items-center gap-2">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  <span>{t('deleteConfirmation.deleting')}</span>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <Trash2 className="h-4 w-4" />
                  <span>
                    {variant === 'bulk' && count > 1 ? t('deleteConfirmation.deleteItems', { count }) : t('deleteConfirmation.delete')}
                  </span>
                </div>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
