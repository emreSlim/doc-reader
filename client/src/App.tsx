import { useEffect, useRef, useState } from 'react'
import UploadPage from './components/UploadPage'
import ProcessingPage from './components/ProcessingPage'
import ReaderPage from './components/ReaderPage'
import type { PageJobResult } from './types'
import { processPdfPagesSequentially, type PageProcessProgress } from './api'

type AppState = 'upload' | 'processing' | 'reader'

export default function App() {
  const [state, setState] = useState<AppState>('upload')
  const [fileName, setFileName] = useState('')
  const [fullPdfUrl, setFullPdfUrl] = useState<string | null>(null)
  const [pages, setPages] = useState<PageJobResult[]>([])
  const [progress, setProgress] = useState<PageProcessProgress | null>(null)
  const [processingError, setProcessingError] = useState<string | null>(null)
  const [isProcessingMore, setIsProcessingMore] = useState(false)
  const runIdRef = useRef(0)
  const fullPdfUrlRef = useRef<string | null>(null)

  useEffect(() => {
    return () => {
      if (fullPdfUrlRef.current) {
        URL.revokeObjectURL(fullPdfUrlRef.current)
        fullPdfUrlRef.current = null
      }
    }
  }, [])

  const handleStartProcessing = (file: File) => {
    let firstPageDelivered = false

    const runId = runIdRef.current + 1
    runIdRef.current = runId

    if (fullPdfUrlRef.current) {
      URL.revokeObjectURL(fullPdfUrlRef.current)
      fullPdfUrlRef.current = null
    }
    const nextFullPdfUrl = URL.createObjectURL(file)
    fullPdfUrlRef.current = nextFullPdfUrl
    setFullPdfUrl(nextFullPdfUrl)

    setFileName(file.name)
    setPages([])
    setProgress(null)
    setProcessingError(null)
    setIsProcessingMore(true)
    setState('processing')

    processPdfPagesSequentially(
      file,
      (p) => {
        if (runIdRef.current !== runId) return
        setProgress(p)
      },
      (page) => {
        if (runIdRef.current !== runId) return
        firstPageDelivered = true
        setPages((prev) => {
          const next = [...prev, page].sort((a, b) => a.pageIndex - b.pageIndex)
          if (next.length === 1) {
            setState('reader')
          }
          return next
        })
      },
    )
      .then((allPages) => {
        if (runIdRef.current !== runId) return
        setPages(allPages)
        setIsProcessingMore(false)
        setProcessingError(null)
        if (allPages.length > 0) {
          setState('reader')
        }
      })
      .catch((err) => {
        if (runIdRef.current !== runId) return
        setIsProcessingMore(false)
        const msg = err instanceof Error ? err.message : 'Processing failed'
        if (!firstPageDelivered) {
          setProcessingError(msg)
          setState('processing')
        } else {
          setProcessingError(msg)
          setState('reader')
        }
      })
  }

  const handleReset = () => {
    runIdRef.current += 1
    if (fullPdfUrlRef.current) {
      URL.revokeObjectURL(fullPdfUrlRef.current)
      fullPdfUrlRef.current = null
    }
    setFileName('')
    setFullPdfUrl(null)
    setPages([])
    setProgress(null)
    setProcessingError(null)
    setIsProcessingMore(false)
    setState('upload')
  }

  return (
    <div className="h-screen bg-gray-950 text-gray-100">
      {state === 'upload' && (
        <UploadPage onStartProcessing={handleStartProcessing} />
      )}
      {state === 'processing' && (
        <ProcessingPage
          fileName={fileName}
          progress={progress}
          error={processingError}
          onError={handleReset}
        />
      )}
      {state === 'reader' && pages.length > 0 && fullPdfUrl && (
        <ReaderPage
          fileName={fileName}
          pages={pages}
          fullPdfUrl={fullPdfUrl}
          isProcessingMore={isProcessingMore}
          processingError={processingError}
          progress={progress}
          onBack={handleReset}
        />
      )}
    </div>
  )
}
