import { useMemo, useRef, useState } from 'react'
import PdfViewer from './PdfViewer'
import TextPanel from './TextPanel'
import AudioPlayer from './AudioPlayer'
import type { AlignedWord, ChunkTiming, WordAlignmentPayload } from '../types'

interface Props {
  fileName: string
  chunkTiming: ChunkTiming[]
  alignment: WordAlignmentPayload | null
  audioUrl: string
  pdfUrl: string
  onBack: () => void
}

function findActiveWord(words: AlignedWord[], currentTime: number): AlignedWord | null {
  if (!words.length) return null
  let lo = 0
  let hi = words.length - 1
  let best = -1
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2)
    if (words[mid].start <= currentTime) {
      best = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  if (best < 0) return null
  const w = words[best]
  if (currentTime >= w.start - 0.02 && currentTime <= w.end + 0.02) return w
  return null
}

export default function ReaderPage({ fileName, chunkTiming, alignment, audioUrl, pdfUrl, onBack }: Props) {
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const audioRef = useRef<HTMLAudioElement>(null)

  // Find the active chunk index from current playback time
  const activeChunkIndex = useMemo(() => {
    if (!chunkTiming.length) return -1
    let active = -1
    for (let i = 0; i < chunkTiming.length; i++) {
      if (chunkTiming[i].start <= currentTime) active = i
      else break
    }
    return active
  }, [chunkTiming, currentTime])

  const activeWord = useMemo(
    () => findActiveWord(alignment?.words ?? [], currentTime),
    [alignment, currentTime],
  )

  return (
    <div className="h-screen flex flex-col bg-gray-950 overflow-hidden">
      {/* ── Top bar ── */}
      <header className="shrink-0 h-14 bg-gray-900 border-b border-gray-800 flex items-center px-4 gap-3">
        <button
          onClick={onBack}
          className="text-gray-400 hover:text-white transition-colors p-1 rounded-lg hover:bg-gray-700"
          title="Upload new PDF"
        >
          ← New PDF
        </button>
        <div className="w-px h-5 bg-gray-700" />
        <span className="text-sm font-medium text-gray-200 truncate">{fileName}</span>
        <div className="ml-auto flex items-center gap-2 text-xs text-gray-500">
          {chunkTiming.length} chunks
          <span>· {alignment?.words?.length ?? 0} aligned words</span>
          <span>· {alignment?.timing_source ?? 'estimated-chunk'}</span>
          {duration > 0 && (
            <span>· {Math.round(duration / 60)}m audio</span>
          )}
        </div>
      </header>

      {/* ── Main panels ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* PDF viewer — left 55% */}
        <div className="w-[55%] border-r border-gray-800 overflow-y-auto bg-gray-900">
          <PdfViewer
            pdfUrl={pdfUrl}
            activeWord={activeWord}
          />
        </div>

        {/* Text panel — right 45% */}
        <div className="w-[45%] overflow-y-auto">
          <TextPanel
            chunkTiming={chunkTiming}
            activeChunkIndex={activeChunkIndex}
            onChunkClick={(idx: number) => {
              if (audioRef.current) {
                audioRef.current.currentTime = chunkTiming[idx].start
              }
            }}
          />
        </div>
      </div>

      {/* ── Audio player bar ── */}
      <div className="shrink-0 border-t border-gray-800 bg-gray-900">
        <AudioPlayer
          audioRef={audioRef}
          audioUrl={audioUrl}
          currentTime={currentTime}
          duration={duration}
          isPlaying={isPlaying}
          onTimeUpdate={setCurrentTime}
          onDurationChange={setDuration}
          onPlayStateChange={setIsPlaying}
        />
      </div>
    </div>
  )
}
