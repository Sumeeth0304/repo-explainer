export interface RepoOverview {
  repo_id: string
  repo_name: string
  description?: string
  files_processed: number
  chunks_stored: number
  status: string
  what_it_does?: string
  architecture?: string
  key_modules?: string[]
  api_flows?: string
  tech_stack?: string[]
  interesting_patterns?: string
}

export interface CodeChunk {
  file_path: string
  content: string
  language: string
  score: number
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: CodeChunk[]
}
