import { useEffect, useMemo, useRef, useState } from 'react'
import PdfViewer from './PdfViewer'
import TextPanel from './TextPanel'
import AudioPlayer from './AudioPlayer'
import { getAudioUrl } from '../api'
import type { AlignedWord, PageJobResult } from '../types'
import type { PageProcessProgress } from '../api'

interface Props {
  fileName: string
  pages: PageJobResult[]
  fullPdfUrl: string
  isProcessingMore?: boolean
  processingError?: string | null
  progress?: PageProcessProgress | null
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

export default function ReaderPage({ fileName, pages, fullPdfUrl, isProcessingMore = false, processingError = null, progress = null, onBack }: Props) {
  const [currentPageIndex, setCurrentPageIndex] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [showTextPanel, setShowTextPanel] = useState(true)
  const autoPlayPendingRef = useRef(false)
  const audioRef = useRef<HTMLAudioElement>(null)
  const totalUploadedPages = progress?.pageCount && progress.pageCount > 0 ? progress.pageCount : pages.length

  const currentPage = pages[currentPageIndex]
  const chunkTiming = currentPage?.chunkTiming ?? []
  const alignment = currentPage?.alignment ?? null
  const audioUrl = currentPage ? getAudioUrl(currentPage.jobId) : ''

  useEffect(() => {
    setCurrentTime(0)
    setDuration(0)
  }, [currentPageIndex])

  useEffect(() => {
    const audio = audioRef.current
    if (!autoPlayPendingRef.current || !audio) return

    let cancelled = false
    const tryPlay = () => {
      if (cancelled || !autoPlayPendingRef.current) return
      audio.play()
        .then(() => {
          autoPlayPendingRef.current = false
        })
        .catch(() => {
          // If policy/network timing blocks immediate play, next canplay can retry.
        })
    }

    if (audio.readyState >= 2) {
      tryPlay()
      return
    }

    const onReady = () => tryPlay()
    audio.addEventListener('canplay', onReady)
    audio.addEventListener('loadedmetadata', onReady)
    return () => {
      cancelled = true
      audio.removeEventListener('canplay', onReady)
      audio.removeEventListener('loadedmetadata', onReady)
    }
  }, [currentPageIndex, audioUrl])

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

  const activeWord = useMemo(() => {
    const local = findActiveWord(alignment?.words ?? [], currentTime)
    if (!local) return null
    return {
      ...local,
      page_index: currentPageIndex,
    }
  }, [alignment, currentTime, currentPageIndex])

  const goToPage = (nextIndex: number, autoPlay: boolean = false) => {
    if (nextIndex < 0 || nextIndex >= pages.length) return
    if (autoPlay) autoPlayPendingRef.current = true
    setCurrentPageIndex(nextIndex)
  }

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
          <span>Audio page {currentPageIndex + 1}/{pages.length}</span>
          <span>· PDF pages: {totalUploadedPages}</span>
          {chunkTiming.length} chunks
          <span>· {alignment?.words?.length ?? 0} aligned words</span>
          <span>· {alignment?.timing_source ?? 'estimated-chunk'}</span>
          {duration > 0 && (
            <span>· {Math.round(duration / 60)}m audio</span>
          )}
        </div>
      </header>

      <div className="shrink-0 h-10 bg-gray-900 border-b border-gray-800 px-4 flex items-center gap-2 text-xs">
        {isProcessingMore && (
          <span className="px-2 py-1 rounded bg-indigo-900/50 border border-indigo-700 text-indigo-300">
            Processing next pages… {progress?.pageCount ? `${Math.min(progress.pageIndex + 1, progress.pageCount)}/${progress.pageCount}` : ''}
          </span>
        )}
        {processingError && (
          <span className="px-2 py-1 rounded bg-red-900/40 border border-red-700 text-red-300">
            Background processing error: {processingError}
          </span>
        )}
        <button
          onClick={() => goToPage(currentPageIndex - 1)}
          disabled={currentPageIndex === 0}
          className="px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ← Prev page
        </button>
        <button
          onClick={() => goToPage(currentPageIndex + 1)}
          disabled={currentPageIndex >= pages.length - 1}
          className="px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next page →
        </button>
        <button
          onClick={() => setShowTextPanel((v) => !v)}
          className="ml-auto px-2 py-1 rounded bg-gray-800 hover:bg-gray-700"
        >
          {showTextPanel ? 'Hide text panel' : 'Show text panel'}
        </button>
      </div>

      {/* ── Main panels ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* PDF viewer — left 55% */}
        <div className={`${showTextPanel ? 'w-[55%] border-r border-gray-800' : 'w-full'} overflow-y-auto bg-gray-900`}>
          <PdfViewer
            pdfUrl={fullPdfUrl}
            activeWord={activeWord}
          />
        </div>

        {/* Text panel — right 45% */}
        {showTextPanel && (
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
        )}
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
          onEnded={() => {
            if (currentPageIndex < pages.length - 1) {
              goToPage(currentPageIndex + 1, true)
            }
          }}
        />
      </div>
    </div>
  )
}
