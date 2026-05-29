import { useEffect, useMemo, useState } from 'react'
import type { PageProcessProgress } from '../api'

interface Props {
  fileName: string
  progress: PageProcessProgress | null
  error: string | null
  onError: () => void
}

const STAGES = [
  'Splitting PDF into pages…',
  'Uploading current page…',
  'Processing current page…',
  'Fetching block polygons…',
  'Finalizing…',
]

function stageFromProgress(progress: PageProcessProgress | null): number {
  if (!progress) return 0
  switch (progress.phase) {
    case 'splitting':
      return 0
    case 'uploading':
      return 1
    case 'processing':
      return 2
    case 'metadata':
      return 3
    case 'done':
      return 4
    default:
      return 0
  }
}

export default function ProcessingPage({ fileName, progress, error, onError }: Props) {
  const [stageIndex, setStageIndex] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  // Elapsed time counter
  useEffect(() => {
    const tick = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [])

  useEffect(() => {
    setStageIndex(stageFromProgress(progress))
  }, [progress])

  const mins = Math.floor(elapsed / 60)
  const secs = elapsed % 60
  const totalPages = progress?.pageCount ?? 0
  const completedPages = progress?.phase === 'done'
    ? (progress.pageCount ?? 0)
    : progress
    ? progress.pageIndex
    : 0
  const pageLabel = useMemo(() => {
    if (!progress || !progress.pageCount) return 'Preparing pages...'
    if (progress.phase === 'done') return `Completed ${progress.pageCount}/${progress.pageCount} pages`
    return `Page ${progress.pageIndex + 1}/${progress.pageCount}`
  }, [progress])

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
            <p className="text-gray-400 text-xs mt-2">{pageLabel}</p>
            {totalPages > 0 && (
              <div className="mt-3">
                <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-2 bg-indigo-500"
                    style={{ width: `${Math.min(100, (completedPages / totalPages) * 100)}%` }}
                  />
                </div>
              </div>
            )}
            <p className="text-gray-600 text-xs mt-3">
              {mins > 0 ? `${mins}m ` : ''}{secs}s elapsed · processing pages one-by-one
            </p>
            {progress?.jobId && (
              <p className="text-gray-700 text-xs mt-6 font-mono">Job: {progress.jobId.slice(0, 8)}…</p>
            )}
          </>
        )}
      </div>
    </div>
  )
}
