import { PDFDocument } from 'pdf-lib'
import type { ExtractionMetadata, JobResult, PageJobResult, WordAlignmentPayload } from './types'

export async function uploadAndProcess(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  form.append('generate_mp3', 'true')

  const res = await fetch('/api/v1/process', { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Upload failed: ${text}`)
  }
  const data = await res.json()
  return data.job_id as string
}

async function splitPdfIntoSinglePageFiles(file: File): Promise<File[]> {
  const inputBytes = await file.arrayBuffer()
  const sourceDoc = await PDFDocument.load(inputBytes)
  const pageCount = sourceDoc.getPageCount()
  const pages: File[] = []

  for (let i = 0; i < pageCount; i++) {
    const pageDoc = await PDFDocument.create()
    const [copiedPage] = await pageDoc.copyPages(sourceDoc, [i])
    pageDoc.addPage(copiedPage)
    const bytes = await pageDoc.save()
    const byteCopy = new Uint8Array(bytes)
    pages.push(new File([byteCopy], `${file.name.replace(/\.pdf$/i, '')}_page_${i + 1}.pdf`, { type: 'application/pdf' }))
  }

  return pages
}

export async function pollJob(jobId: string): Promise<JobResult> {
  const res = await fetch(`/api/v1/jobs/${jobId}`)
  if (!res.ok) throw new Error(`Poll failed: ${await res.text()}`)
  return res.json() as Promise<JobResult>
}

async function waitForJobDone(jobId: string, intervalMs: number = 3000): Promise<JobResult> {
  while (true) {
    const result = await pollJob(jobId)
    if (result.status === 'done') return result
    if (result.status === 'error') {
      throw new Error(result.error ?? `Page job failed: ${jobId}`)
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}

export interface PageProcessProgress {
  pageIndex: number
  pageCount: number
  phase: 'splitting' | 'uploading' | 'processing' | 'metadata' | 'done'
  jobId?: string
}

export async function processPdfPagesSequentially(
  file: File,
  onProgress?: (p: PageProcessProgress) => void,
  onPageDone?: (page: PageJobResult) => void,
): Promise<PageJobResult[]> {
  onProgress?.({ pageIndex: 0, pageCount: 0, phase: 'splitting' })
  const pageFiles = await splitPdfIntoSinglePageFiles(file)
  const total = pageFiles.length
  const results: PageJobResult[] = []

  for (let i = 0; i < total; i++) {
    const pageFile = pageFiles[i]
    onProgress?.({ pageIndex: i, pageCount: total, phase: 'uploading' })
    const jobId = await uploadAndProcess(pageFile)

    onProgress?.({ pageIndex: i, pageCount: total, phase: 'processing', jobId })
    const done = await waitForJobDone(jobId)

    onProgress?.({ pageIndex: i, pageCount: total, phase: 'metadata', jobId })
    let extractionMeta: ExtractionMetadata | null = null
    try {
      extractionMeta = await fetchExtractionMetadata(jobId)
    } catch {
      extractionMeta = null
    }

    let alignment: WordAlignmentPayload | null = null
    try {
      alignment = await fetchAlignment(jobId)
    } catch {
      alignment = null
    }

    const pageResult: PageJobResult = {
      pageIndex: i,
      pageNumber: i + 1,
      jobId,
      chunkTiming: done.chunk_timing ?? [],
      extractionMeta,
      alignment,
    }
    results.push(pageResult)
    onPageDone?.(pageResult)
  }

  onProgress?.({ pageIndex: total - 1, pageCount: total, phase: 'done', jobId: results[total - 1]?.jobId })
  return results
}

export async function fetchExtractionMetadata(jobId: string): Promise<ExtractionMetadata> {
  const res = await fetch(`/api/v1/jobs/${jobId}/metadata`)
  if (!res.ok) throw new Error(`Metadata fetch failed: ${await res.text()}`)
  return res.json() as Promise<ExtractionMetadata>
}

export async function fetchAlignment(jobId: string): Promise<WordAlignmentPayload> {
  const res = await fetch(`/api/v1/jobs/${jobId}/alignment`)
  if (!res.ok) throw new Error(`Alignment fetch failed: ${await res.text()}`)
  return res.json() as Promise<WordAlignmentPayload>
}

export function getAudioUrl(jobId: string): string {
  return `/api/v1/jobs/${jobId}/audio`
}

export function getPdfUrl(jobId: string): string {
  return `/api/v1/jobs/${jobId}/pdf`
}
