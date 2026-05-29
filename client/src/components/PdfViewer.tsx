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
  const rootRef = useRef<HTMLDivElement | null>(null)

  const containerRef = useCallback((node: HTMLDivElement | null) => {
    rootRef.current = node
    if (node) setContainerWidth(node.clientWidth - 32)
  }, [])

  useEffect(() => {
    if (!activeWord || !rootRef.current) return
    const pageEl = rootRef.current.querySelector(`[data-page="${activeWord.page_index + 1}"]`)
    if (pageEl instanceof HTMLElement) {
      pageEl.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [activeWord])

  return (
    <div ref={containerRef} className="p-4 flex flex-col items-center gap-4">
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
                renderTextLayer={true}
                renderAnnotationLayer={false}
              />

              {activeWord && activeWord.page_index === i && (
                <div className="absolute inset-0 pointer-events-none z-20">
                  <div
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
