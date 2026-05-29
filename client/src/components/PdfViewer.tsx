import { useState, useCallback, useEffect, useRef } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
// Use CDN worker to avoid Vite bundling issues with PDF.js
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

export interface ChunkBbox {
  page_index: number
  polygon: [number, number][]
  normalized?: boolean
}

interface Props {
  pdfUrl: string
  activeChunkBboxes: ChunkBbox[] | null
}

export default function PdfViewer({ pdfUrl, activeChunkBboxes }: Props) {
  const [numPages, setNumPages] = useState<number>(0)
  const [pageSizes, setPageSizes] = useState<Record<number, { width: number; height: number }>>({})
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
    if (!activeChunkBboxes?.length || !rootRef.current) return

    const scrollContainer = rootRef.current.parentElement
    if (!(scrollContainer instanceof HTMLElement)) return

    const marker = rootRef.current.querySelector('[data-active-block="true"]')
    if (!marker) return

    const cRect = scrollContainer.getBoundingClientRect()
    const mRect = marker.getBoundingClientRect()
    const topMargin = 90
    const bottomMargin = 130
    const visibleTop = cRect.top + topMargin
    const visibleBottom = cRect.bottom - bottomMargin

    if (mRect.top >= visibleTop && mRect.bottom <= visibleBottom) return

    const markerMid = (mRect.top + mRect.bottom) / 2
    const visibleMid = (visibleTop + visibleBottom) / 2
    const delta = markerMid - visibleMid

    scrollContainer.scrollBy({ top: delta, behavior: 'smooth' })
  }, [activeChunkBboxes])

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
                onLoadSuccess={(page) => {
                  const view = Array.isArray(page.view) ? page.view : [0, 0, 1, 1]
                  const width = Math.max(1, Math.abs(Number(view[2] ?? 1) - Number(view[0] ?? 0)))
                  const height = Math.max(1, Math.abs(Number(view[3] ?? 1) - Number(view[1] ?? 0)))
                  setPageSizes((prev) => {
                    const current = prev[i]
                    if (current && current.width === width && current.height === height) return prev
                    return { ...prev, [i]: { width, height } }
                  })
                }}
              />

              {activeChunkBboxes?.filter(b => b.page_index === i).map((b, bi) => {
                const pageSize = pageSizes[i]
                if (!pageSize || !b.polygon?.length) return null
                const points = b.polygon
                  .map(([x, y]) => {
                    const px = b.normalized ? x * 100 : (x / pageSize.width) * 100
                    const py = b.normalized ? y * 100 : (y / pageSize.height) * 100
                    return `${px},${py}`
                  })
                  .join(' ')
                return (
                <div key={bi} className="absolute inset-0 pointer-events-none z-20">
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full">
                    <polygon
                      data-active-block="true"
                      points={points}
                      fill="rgba(250, 204, 21, 0.14)"
                      stroke="rgba(245, 158, 11, 0.85)"
                      strokeWidth="0.08"
                    />
                  </svg>
                </div>
                )
              })}
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
