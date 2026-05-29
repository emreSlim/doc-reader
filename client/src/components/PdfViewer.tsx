import { useState, useCallback, useEffect, useRef } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import type { AlignedWord } from '../types'
// Use CDN worker to avoid Vite bundling issues with PDF.js
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface Props {
  pdfUrl: string
  activeWord: AlignedWord | null
}

export default function PdfViewer({ pdfUrl, activeWord }: Props) {
  const [numPages, setNumPages] = useState<number>(0)
  const [containerWidth, setContainerWidth] = useState(600)
  const [zoom, setZoom] = useState(1)
  const rootRef = useRef<HTMLDivElement | null>(null)

  const ZOOM_MIN = 0.6
  const ZOOM_MAX = 2.5
  const ZOOM_STEP = 0.2

  const containerRef = useCallback((node: HTMLDivElement | null) => {
    rootRef.current = node
    if (node) setContainerWidth(node.clientWidth - 32)
  }, [])

  useEffect(() => {
    if (!activeWord || !rootRef.current) return

    // Scroll only when highlight is near/outside viewport bounds.
    // This avoids constant page recentering on every word.
    const scrollContainer = rootRef.current.parentElement
    if (!(scrollContainer instanceof HTMLElement)) return

    const marker = rootRef.current.querySelector('[data-active-word="true"]')
    if (!(marker instanceof HTMLElement)) return

    const cRect = scrollContainer.getBoundingClientRect()
    const mRect = marker.getBoundingClientRect()
    const topMargin = 90
    const bottomMargin = 130

    if (mRect.top < cRect.top + topMargin) {
      const delta = (cRect.top + topMargin) - mRect.top
      scrollContainer.scrollBy({ top: -delta, behavior: 'smooth' })
      return
    }

    if (mRect.bottom > cRect.bottom - bottomMargin) {
      const delta = mRect.bottom - (cRect.bottom - bottomMargin)
      scrollContainer.scrollBy({ top: delta, behavior: 'smooth' })
    }
  }, [activeWord])

  return (
    <div ref={containerRef} className="p-4 flex flex-col items-center gap-4">
      <div className="sticky top-2 z-30 w-full max-w-3xl flex justify-end">
        <div className="flex items-center gap-2 bg-gray-900/90 border border-gray-700 rounded-lg px-2 py-1 shadow">
          <button
            onClick={() => setZoom((z) => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2)))}
            className="px-2 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700"
            title="Zoom out"
          >
            −
          </button>
          <span className="text-xs text-gray-300 min-w-12 text-center">{Math.round(zoom * 100)}%</span>
          <button
            onClick={() => setZoom((z) => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2)))}
            className="px-2 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700"
            title="Zoom in"
          >
            +
          </button>
          <button
            onClick={() => setZoom(1)}
            className="px-2 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700"
            title="Reset zoom"
          >
            Reset
          </button>
        </div>
      </div>

      <Document
        file={pdfUrl}
        onLoadSuccess={({ numPages }) => setNumPages(numPages)}
        onLoadError={(err) => console.error('PDF load error:', err)}
        loading={
          <div className="flex items-center justify-center h-64 text-gray-500">
            <span className="animate-pulse">Loading PDF…</span>
          </div>
        }
        error={
          <div className="flex items-center justify-center h-64 text-red-400">
            Failed to load PDF
          </div>
        }
      >
        {Array.from({ length: numPages }, (_, i) => (
          <div key={i} className="mb-4 shadow-xl rounded overflow-hidden" data-page={i + 1}>
            <div className="text-xs text-gray-600 text-center py-1 bg-gray-800">
              Page {i + 1}
            </div>
            <div className="relative inline-block">
              <Page
                pageNumber={i + 1}
                width={containerWidth}
                scale={zoom}
                renderTextLayer={true}
                renderAnnotationLayer={false}
              />

              {activeWord && activeWord.page_index === i && (
                <div className="absolute inset-0 pointer-events-none z-20">
                  <div
                    data-active-word="true"
                    style={{
                      position: 'absolute',
                      left: `${activeWord.bbox_norm[0] * 100}%`,
                      top: `${activeWord.bbox_norm[1] * 100}%`,
                      width: `${(activeWord.bbox_norm[2] - activeWord.bbox_norm[0]) * 100}%`,
                      height: `${(activeWord.bbox_norm[3] - activeWord.bbox_norm[1]) * 100}%`,
                      background: 'rgba(59, 130, 246, 0.42)',
                      border: '1px solid rgba(37, 99, 235, 0.9)',
                      borderRadius: '3px',
                      boxShadow: '0 0 0 1px rgba(255,255,255,0.16) inset',
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        ))}
      </Document>

      {numPages === 0 && (
        <p className="text-gray-600 text-sm">No pages loaded yet.</p>
      )}
    </div>
  )
}
