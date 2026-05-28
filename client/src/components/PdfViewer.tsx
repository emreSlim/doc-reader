import { useState, useCallback } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
// Use CDN worker to avoid Vite bundling issues with PDF.js
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface Props {
  pdfUrl: string
  activeChunkText: string
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export default function PdfViewer({ pdfUrl, activeChunkText }: Props) {
  const [numPages, setNumPages] = useState<number>(0)
  const [containerWidth, setContainerWidth] = useState(600)

  const terms = Array.from(
    new Set(
      activeChunkText
        .toLowerCase()
        .split(/[^a-z0-9']+/)
        .filter((t) => t.length >= 5)
        .slice(0, 12),
    ),
  )

  const containerRef = useCallback((node: HTMLDivElement | null) => {
    if (node) setContainerWidth(node.clientWidth - 32)
  }, [])

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
            <Page
              pageNumber={i + 1}
              width={containerWidth}
              renderTextLayer={true}
              renderAnnotationLayer={false}
              customTextRenderer={({ str }: { str: string }) => {
                let html = str
                for (const term of terms) {
                  const re = new RegExp(`(${escapeRegex(term)})`, 'ig')
                  html = html.replace(
                    re,
                    '<mark style="background:#fef08a;color:#111827;padding:0 2px;border-radius:2px;">$1</mark>',
                  )
                }
                return html
              }}
            />
          </div>
        ))}
      </Document>

      {numPages === 0 && (
        <p className="text-gray-600 text-sm">No pages loaded yet.</p>
      )}
    </div>
  )
}
