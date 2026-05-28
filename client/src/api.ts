import type { JobResult } from './types'

export async function uploadAndProcess(file: File): Promise<string> {
  const form = new FormData()
  form.append('file', file)
  form.append('fast', 'true')
  form.append('generate_mp3', 'true')

  const res = await fetch('/api/v1/process', { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Upload failed: ${text}`)
  }
  const data = await res.json()
  return data.job_id as string
}

export async function pollJob(jobId: string): Promise<JobResult> {
  const res = await fetch(`/api/v1/jobs/${jobId}`)
  if (!res.ok) throw new Error(`Poll failed: ${await res.text()}`)
  return res.json() as Promise<JobResult>
}

export function getAudioUrl(jobId: string): string {
  return `/api/v1/jobs/${jobId}/audio`
}

export function getPdfUrl(jobId: string): string {
  return `/api/v1/jobs/${jobId}/pdf`
}
