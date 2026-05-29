import { useEffect, useState } from 'react'
import { fetchAlignment, pollJob } from '../api'
import type { ChunkTiming, WordAlignmentPayload } from '../types'

interface Props {
  jobId: string
  fileName: string
  onDone: (chunks: ChunkTiming[], alignment: WordAlignmentPayload | null) => void
  onError: () => void
}

const STAGES = [
  'Extracting text from PDF…',
  'Detecting layout regions…',
  'Cleaning and chunking text…',
  'Generating audio with Piper TTS…',
  'Merging audio tracks…',
  'Almost done…',
]

export default function ProcessingPage({ jobId, fileName, onDone, onError }: Props) {
  const [stageIndex, setStageIndex] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [elapsed, setElapsed] = useState(0)

  // Cycle through stage labels every ~8 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, STAGES.length - 1))
    }, 8000)
    return () => clearInterval(interval)
  }, [])

  // Elapsed time counter
  useEffect(() => {
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [])

  // Poll job status
  useEffect(() => {
    const poll = setInterval(async () => {
      try {
        const result = await pollJob(jobId)
        if (result.status === 'done') {
          clearInterval(poll)
          let alignment: WordAlignmentPayload | null = null
          try {
            alignment = await fetchAlignment(jobId)
          } catch (alignErr) {
            console.warn('Alignment unavailable for job', jobId, alignErr)
            alignment = null
          }
          onDone(result.chunk_timing ?? [], alignment)
        } else if (result.status === 'error') {
          clearInterval(poll)
          setError(result.error ?? 'Processing failed')
        }
      } catch (err) {
        clearInterval(poll)
        setError(err instanceof Error ? err.message : 'Network error')
      }
    }, 3000)
    return () => clearInterval(poll)
  }, [jobId, onDone])

  const mins = Math.floor(elapsed / 60)
  const secs = elapsed % 60

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-md text-center">
        {error ? (
          <>
            <div className="text-5xl mb-4">⚠️</div>
            <h2 className="text-xl font-semibold text-red-400 mb-2">Processing failed</h2>
            <p className="text-gray-400 text-sm mb-6">{error}</p>
            <button
              onClick={onError}
              className="px-6 py-2 rounded-xl bg-gray-700 hover:bg-gray-600 text-white font-medium"
            >
              ← Try again
            </button>
          </>
        ) : (
          <>
            {/* Animated book icon */}
            <div className="flex justify-center mb-8">
              <div className="relative w-24 h-24">
                <div className="absolute inset-0 rounded-full bg-indigo-600/20 animate-ping" />
                <div className="relative flex items-center justify-center w-24 h-24 rounded-full bg-indigo-900/60 text-5xl">
                  📖
                </div>
              </div>
            </div>

            <h2 className="text-xl font-semibold text-white mb-1">Processing your PDF</h2>
            <p className="text-gray-400 text-sm mb-6 truncate max-w-xs mx-auto">{fileName}</p>

            {/* Progress dots */}
            <div className="flex justify-center gap-1.5 mb-8">
              {STAGES.map((_, i) => (
                <div
                  key={i}
                  className={`h-1.5 rounded-full transition-all duration-500 ${
                    i < stageIndex
                      ? 'w-4 bg-indigo-400'
                      : i === stageIndex
                      ? 'w-8 bg-indigo-500 animate-pulse'
                      : 'w-4 bg-gray-700'
                  }`}
                />
              ))}
            </div>

            <p className="text-indigo-300 text-sm font-medium">{STAGES[stageIndex]}</p>
            <p className="text-gray-600 text-xs mt-3">
              {mins > 0 ? `${mins}m ` : ''}{secs}s elapsed · TTS generation can take a few minutes
            </p>

            <p className="text-gray-700 text-xs mt-6 font-mono">Job: {jobId.slice(0, 8)}…</p>
          </>
        )}
      </div>
    </div>
  )
}
