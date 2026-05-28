import { useEffect, useRef, useState } from 'react'

interface Props {
  audioRef: React.RefObject<HTMLAudioElement>
  audioUrl: string
  currentTime: number
  duration: number
  isPlaying: boolean
  onTimeUpdate: (t: number) => void
  onDurationChange: (d: number) => void
  onPlayStateChange: (playing: boolean) => void
}

const SPEEDS = [0.75, 1, 1.25, 1.5, 2] as const

export default function AudioPlayer({
  audioRef,
  audioUrl,
  currentTime,
  duration,
  isPlaying,
  onTimeUpdate,
  onDurationChange,
  onPlayStateChange,
}: Props) {
  const [speed, setSpeed] = useState(1)
  const seeking = useRef(false)

  // Sync playback rate
  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = speed
  }, [speed, audioRef])

  const handlePlayPause = () => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      audio.play()
    } else {
      audio.pause()
    }
  }

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value)
    if (audioRef.current) audioRef.current.currentTime = val
    onTimeUpdate(val)
  }

  const skipSeconds = (sec: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = Math.max(0, Math.min(duration, currentTime + sec))
    }
  }

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div className="px-6 py-3 flex items-center gap-4">
      {/* Hidden audio element */}
      <audio
        ref={audioRef}
        src={audioUrl}
        preload="metadata"
        onTimeUpdate={() => {
          if (!seeking.current && audioRef.current)
            onTimeUpdate(audioRef.current.currentTime)
        }}
        onLoadedMetadata={() => audioRef.current && onDurationChange(audioRef.current.duration)}
        onPlay={() => onPlayStateChange(true)}
        onPause={() => onPlayStateChange(false)}
        onEnded={() => onPlayStateChange(false)}
      />

      {/* Skip back 10s */}
      <button
        onClick={() => skipSeconds(-10)}
        className="text-gray-400 hover:text-white transition-colors text-sm w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-700"
        title="Back 10s"
      >
        ↩ 10
      </button>

      {/* Play / Pause */}
      <button
        onClick={handlePlayPause}
        className="w-10 h-10 rounded-full bg-indigo-600 hover:bg-indigo-500 active:scale-95 transition-all flex items-center justify-center text-white shadow-lg"
      >
        {isPlaying ? (
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
            <rect x="6" y="4" width="4" height="16" />
            <rect x="14" y="4" width="4" height="16" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 ml-0.5">
            <path d="M8 5v14l11-7z" />
          </svg>
        )}
      </button>

      {/* Skip forward 10s */}
      <button
        onClick={() => skipSeconds(10)}
        className="text-gray-400 hover:text-white transition-colors text-sm w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-700"
        title="Forward 10s"
      >
        10 ↪
      </button>

      {/* Time / seek */}
      <div className="flex-1 flex items-center gap-3 min-w-0">
        <span className="text-xs text-gray-500 font-mono w-10 shrink-0 text-right">
          {formatTime(currentTime)}
        </span>

        <div className="flex-1 relative">
          {/* Progress fill overlay */}
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-indigo-600/30 pointer-events-none"
            style={{ width: `${progress}%` }}
          />
          <input
            type="range"
            min={0}
            max={duration || 100}
            step={0.1}
            value={currentTime}
            onChange={handleSeek}
            onMouseDown={() => { seeking.current = true }}
            onMouseUp={() => { seeking.current = false }}
            className="w-full"
          />
        </div>

        <span className="text-xs text-gray-500 font-mono w-10 shrink-0">
          {formatTime(duration)}
        </span>
      </div>

      {/* Speed selector */}
      <div className="flex items-center gap-1">
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => setSpeed(s)}
            className={`text-xs px-2 py-1 rounded-lg font-medium transition-colors ${
              speed === s
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-700'
            }`}
          >
            {s}×
          </button>
        ))}
      </div>
    </div>
  )
}

function formatTime(seconds: number): string {
  if (!seconds || isNaN(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}
