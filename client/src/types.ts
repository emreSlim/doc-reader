export interface ChunkTiming {
  index: number
  text: string
  start: number
  end: number
}

export type JobStatus = 'processing' | 'done' | 'error'

export interface JobResult {
  job_id: string
  status: JobStatus
  error?: string
  chunk_timing: ChunkTiming[]
  has_mp3: boolean
  pdf_name: string
}
