import React, { useState } from 'react'
import { Button } from '../../../components/ui/button'
import { Input } from '../../../components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select'
import { Plus, Search, BookOpen, ExternalLink, Copy, Trash2 } from 'lucide-react'

interface Reference {
  id: string
  title: string
  authors: string[]
  year: number
  type: 'journal' | 'book' | 'conference' | 'web'
  url?: string
  doi?: string
}

interface ReferencePanelProps {
  references: Reference[]
}

export const ReferencePanel: React.FC<ReferencePanelProps> = ({ references }) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [citationStyle, setCitationStyle] = useState('apa')
  const [showAddForm, setShowAddForm] = useState(false)

  const filteredReferences = references.filter(ref =>
    ref.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    ref.authors.some(author => author.toLowerCase().includes(searchTerm.toLowerCase()))
  )

  const formatCitation = (ref: Reference, style: string) => {
    const authorsStr = ref.authors.join(', ')
    switch (style) {
      case 'apa':
        return `${authorsStr} (${ref.year}). ${ref.title}.`
      case 'mla':
        return `${authorsStr}. "${ref.title}." ${ref.year}.`
      case 'chicago':
        return `${authorsStr}. "${ref.title}." Accessed ${ref.year}.`
      default:
        return `${authorsStr} (${ref.year}). ${ref.title}.`
    }
  }

  const handleCopyCitation = (citation: string) => {
    navigator.clipboard.writeText(citation)
    // TODO: Show toast notification
    console.log('Citation copied to clipboard')
  }

  const handleAddReference = () => {
    // TODO: Implement add reference functionality
    console.log('Adding new reference...')
    setShowAddForm(true)
  }

  const handleDeleteReference = (refId: string) => {
    // TODO: Implement delete reference functionality
    console.log('Deleting reference:', refId)
  }

  return (
    <div className="h-full flex flex-col p-4">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">References</h3>
          <Button onClick={handleAddReference} size="sm">
            <Plus className="h-4 w-4 mr-2" />
            Add Reference
          </Button>
        </div>

        {/* Search and Style Controls */}
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search references..."
              className="pl-10"
            />
          </div>
          
          <div className="flex items-center space-x-2">
            <label className="text-sm font-medium text-gray-700">Citation Style:</label>
            <Select value={citationStyle} onValueChange={setCitationStyle}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="apa">APA</SelectItem>
                <SelectItem value="mla">MLA</SelectItem>
                <SelectItem value="chicago">Chicago</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* References List */}
        <div className="flex-1 overflow-y-auto space-y-3">
          {filteredReferences.length === 0 ? (
            <Card>
              <CardContent className="p-6">
                <div className="text-center text-gray-500">
                  <BookOpen className="h-12 w-12 mx-auto mb-4 text-gray-400" />
                  <h4 className="text-lg font-medium text-gray-900 mb-2">No References</h4>
                  <p className="text-sm">
                    {searchTerm ? 'No references match your search.' : 'Add references to get started with citations.'}
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            filteredReferences.map((ref) => (
              <Card key={ref.id} className="border-l-4 border-l-green-500">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <CardTitle className="text-base font-medium text-gray-900 mb-1">
                        {ref.title}
                      </CardTitle>
                      <p className="text-sm text-gray-600">
                        {ref.authors.join(', ')} • {ref.year} • {ref.type}
                      </p>
                    </div>
                    <div className="flex items-center space-x-1">
                      {ref.url && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => window.open(ref.url, '_blank')}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDeleteReference(ref.id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  <div className="bg-gray-50 p-3 rounded-md">
                    <div className="flex items-start justify-between">
                      <p className="text-sm text-gray-700 flex-1 font-mono">
                        {formatCitation(ref, citationStyle)}
                      </p>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopyCitation(formatCitation(ref, citationStyle))}
                        className="ml-2"
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  {ref.doi && (
                    <p className="text-xs text-gray-500 mt-2">
                      DOI: {ref.doi}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Add Reference Form */}
        {showAddForm && (
          <Card className="border-blue-200 bg-blue-50">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Add New Reference</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input placeholder="Title" />
              <Input placeholder="Authors (comma-separated)" />
              <div className="flex space-x-2">
                <Input placeholder="Year" className="w-24" />
                <Select>
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="journal">Journal</SelectItem>
                    <SelectItem value="book">Book</SelectItem>
                    <SelectItem value="conference">Conference</SelectItem>
                    <SelectItem value="web">Web</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Input placeholder="URL (optional)" />
              <Input placeholder="DOI (optional)" />
              <div className="flex space-x-2">
                <Button size="sm" className="flex-1">
                  Add Reference
                </Button>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => setShowAddForm(false)}
                  className="flex-1"
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Bibliography Section */}
        {filteredReferences.length > 0 && (
          <Card className="bg-gray-50">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Bibliography</CardTitle>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const bibliography = filteredReferences
                      .map(ref => formatCitation(ref, citationStyle))
                      .join('\n\n')
                    navigator.clipboard.writeText(bibliography)
                  }}
                >
                  <Copy className="h-4 w-4 mr-2" />
                  Copy All
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-gray-700 space-y-2 font-mono">
                {filteredReferences.map((ref) => (
                  <p key={ref.id}>
                    {formatCitation(ref, citationStyle)}
                  </p>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
