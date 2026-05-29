export interface ChunkTiming {
  index: number
  text: string
  start: number
  end: number
}

export interface ChunkHighlight {
  chunk_index: number
  page_index: number
  bbox_norm: [number, number, number, number]
  polygon_norm: [number, number][]
  match_score: number
  matched_tokens: number
  query_tokens: number
}

export interface ChunkHighlightPayload {
  pdf_path: string
  chunk_count: number
  highlight_count: number
  coverage: number
  pages: Array<{
    page_index: number
    width: number
    height: number
  }>
  highlights: ChunkHighlight[]
}

export type PolygonPoint = [number, number]

export interface ExtractionMetadataRegion {
  title?: string
  text?: string
  page_id?: number
  page_index?: number
  polygon?: PolygonPoint[]
  bbox?: [number, number, number, number]
  kept?: boolean
}

export interface ExtractionMetadata {
  table_of_contents?: ExtractionMetadataRegion[]
  pages?: Array<{
    page_id?: number
    page_index?: number
    width?: number
    height?: number
    blocks?: ExtractionMetadataRegion[]
  }>
}

export type JobStatus = 'processing' | 'done' | 'error'

export interface JobResult {
  job_id: string
  status: JobStatus
  error?: string
  chunk_timing: ChunkTiming[]
  extraction_metadata_path?: string
  chunk_highlight_path?: string
  chunk_highlight_coverage?: number
  has_mp3: boolean
  pdf_name: string
}

export interface PageJobResult {
  pageIndex: number
  pageNumber: number
  jobId: string
  chunkTiming: ChunkTiming[]
  extractionMeta: ExtractionMetadata | null
  chunkHighlights: ChunkHighlight[] | null
}
