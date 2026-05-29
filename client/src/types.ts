export interface ChunkTiming {
  index: number
  text: string
  start: number
  end: number
}

export interface AlignedWord {
  text: string
  start: number
  end: number
  page_index: number
  bbox: [number, number, number, number]
  bbox_norm: [number, number, number, number]
}

export interface PageDim {
  page_index: number
  width: number
  height: number
}

export interface WordAlignmentPayload {
  pdf_path: string
  timing_source?: 'forced-whisper' | 'estimated-chunk'
  spoken_word_count: number
  pdf_word_count: number
  aligned_word_count: number
  coverage: number
  pages: PageDim[]
  words: AlignedWord[]
}

export type JobStatus = 'processing' | 'done' | 'error'

export interface JobResult {
  job_id: string
  status: JobStatus
  error?: string
  chunk_timing: ChunkTiming[]
  aligned_word_count?: number
  word_alignment_path?: string
  alignment_timing_source?: 'forced-whisper' | 'estimated-chunk'
  has_mp3: boolean
  pdf_name: string
}
