import { useState } from 'react'
import UploadPage from './components/UploadPage'
import ProcessingPage from './components/ProcessingPage'
import ReaderPage from './components/ReaderPage'
import type { ChunkTiming, WordAlignmentPayload } from './types'
import { getAudioUrl, getPdfUrl } from './api'

type AppState = 'upload' | 'processing' | 'reader'

export default function App() {
  const [state, setState] = useState<AppState>('upload')
  const [jobId, setJobId] = useState<string | null>(null)
  const [fileName, setFileName] = useState('')
  const [chunkTiming, setChunkTiming] = useState<ChunkTiming[]>([])
  const [alignment, setAlignment] = useState<WordAlignmentPayload | null>(null)

  const handleJobStarted = (id: string, name: string) => {
    setJobId(id)
    setFileName(name)
    setState('processing')
  }

  const handleJobDone = (chunks: ChunkTiming[], aligned: WordAlignmentPayload | null) => {
    setChunkTiming(chunks)
    setAlignment(aligned)
    setState('reader')
  }

  const handleReset = () => {
    setJobId(null)
    setFileName('')
    setChunkTiming([])
    setAlignment(null)
    setState('upload')
  }

  return (
    <div className="h-screen bg-gray-950 text-gray-100">
      {state === 'upload' && (
        <UploadPage onJobStarted={handleJobStarted} />
      )}
      {state === 'processing' && jobId && (
        <ProcessingPage jobId={jobId} fileName={fileName} onDone={handleJobDone} onError={handleReset} />
      )}
      {state === 'reader' && jobId && (
        <ReaderPage
          fileName={fileName}
          chunkTiming={chunkTiming}
          alignment={alignment}
          audioUrl={getAudioUrl(jobId)}
          pdfUrl={getPdfUrl(jobId)}
          onBack={handleReset}
        />
      )}
    </div>
  )
}
