import { useEffect, useRef } from 'react'
import type { ChunkTiming } from '../types'

interface Props {
  chunkTiming: ChunkTiming[]
  activeChunkIndex: number
  onChunkClick: (index: number) => void
}

export default function TextPanel({ chunkTiming, activeChunkIndex, onChunkClick }: Props) {
  const activeRef = useRef<HTMLDivElement>(null)

  // Auto-scroll active chunk into view
  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [activeChunkIndex])

  if (!chunkTiming.length) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm p-8 text-center">
        No text chunks available.
        <br />
        The PDF may have been processed without text extraction.
      </div>
    )
  }

  return (
    <div className="p-4 space-y-2">
      <p className="text-xs text-gray-600 uppercase tracking-wider font-semibold mb-4 px-1">
        Extracted Text — click any paragraph to jump
      </p>

      {chunkTiming.map((chunk, idx) => {
        const isActive = idx === activeChunkIndex
        const isPast = idx < activeChunkIndex

        return (
          <div
            key={idx}
            ref={isActive ? activeRef : null}
            onClick={() => onChunkClick(idx)}
            className={`
              relative px-4 py-3 rounded-xl cursor-pointer select-none transition-all duration-200
              ${isActive
                ? 'bg-indigo-950 border border-indigo-500 shadow-lg shadow-indigo-950/50'
                : isPast
                ? 'bg-gray-900/40 border border-transparent opacity-50 hover:opacity-80'
                : 'bg-gray-900/60 border border-transparent hover:border-gray-700 hover:bg-gray-800/60'
              }
            `}
          >
            {/* Active indicator bar */}
            {isActive && (
              <div className="absolute left-0 top-3 bottom-3 w-1 bg-indigo-400 rounded-full" />
            )}

            <p
              className={`text-sm leading-relaxed ${
                isActive ? 'text-indigo-100 font-medium' : isPast ? 'text-gray-500' : 'text-gray-300'
              }`}
            >
              {chunk.text}
            </p>

            {isActive && (
              <div className="flex items-center gap-1.5 mt-2">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                <span className="text-xs text-indigo-400 font-medium">Now playing</span>
                <span className="text-xs text-indigo-600 ml-auto">
                  {formatTime(chunk.start)} – {formatTime(chunk.end)}
                </span>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
