import { useCallback, useState } from 'react'

interface Props {
  onStartProcessing: (file: File) => void
}

export default function UploadPage({ onStartProcessing }: Props) {
  const [isDragging, setIsDragging] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)

  const acceptFile = (f: File) => {
    if (f.type === 'application/pdf' || f.name.endsWith('.pdf')) {
      setFile(f)
      setError(null)
    } else {
      setError('Only PDF files are supported.')
    }
  }

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) acceptFile(dropped)
  }, [])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0]
    if (picked) acceptFile(picked)
  }

  const handleSubmit = async () => {
    if (!file) return
    setError(null)
    onStartProcessing(file)
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
      <div className="w-full max-w-lg">
        {/* Logo / title */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-600 mb-4 text-3xl">
            📖
          </div>
          <h1 className="text-3xl font-bold text-white">PDF Reader</h1>
          <p className="text-gray-400 mt-2">Upload a PDF to generate audio and read along</p>
        </div>

        {/* Drop zone */}
        <div
          className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
            isDragging
              ? 'border-indigo-400 bg-indigo-950/40'
              : file
              ? 'border-indigo-600 bg-indigo-950/20'
              : 'border-gray-700 hover:border-gray-500 bg-gray-900/50'
          }`}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => document.getElementById('file-input')?.click()}
        >
          <input
            id="file-input"
            type="file"
            accept=".pdf,application/pdf"
            className="hidden"
            onChange={handleFileInput}
          />

          {file ? (
            <>
              <div className="text-4xl mb-3">📄</div>
              <p className="text-lg font-medium text-indigo-300">{file.name}</p>
              <p className="text-sm text-gray-500 mt-1">
                {(file.size / 1024 / 1024).toFixed(2)} MB — click or drop to replace
              </p>
            </>
          ) : (
            <>
              <div className="text-4xl mb-3">⬆️</div>
              <p className="text-lg font-medium text-gray-300">Drop a PDF here</p>
              <p className="text-sm text-gray-500 mt-1">or click to browse</p>
            </>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mt-4 p-3 rounded-lg bg-red-950/50 border border-red-800 text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          disabled={!file}
          onClick={handleSubmit}
          className={`mt-6 w-full py-3 rounded-xl font-semibold text-white transition-all ${
            !file
              ? 'bg-gray-700 cursor-not-allowed opacity-50'
              : 'bg-indigo-600 hover:bg-indigo-500 active:scale-[0.98]'
          }`}
        >
          Split by pages & Process Sequentially
        </button>
      </div>
    </div>
  )
}
