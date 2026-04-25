import { useState, useRef, useCallback } from 'react'
import client from '@/api/client'

export function useVoiceRecorder(onTranscription: (text: string) => void) {
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const start = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      chunksRef.current = []

      const recorder = new MediaRecorder(stream)
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setProcessing(true)
        try {
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
          const form = new FormData()
          form.append('audio', blob, 'rec.webm')
          const { data } = await client.post('/voice/transcribe', form, {
            headers: { 'Content-Type': undefined },
          })
          if (data.text) onTranscription(data.text)
          else setError('Речь не распознана')
        } catch {
          setError('Ошибка распознавания')
        } finally {
          setProcessing(false)
        }
      }

      recorder.start()
      recorderRef.current = recorder
      setRecording(true)
    } catch (e: unknown) {
      const err = e as { name?: string }
      if (err?.name === 'NotAllowedError' || err?.name === 'PermissionDeniedError') {
        setError('Разрешите доступ к микрофону в настройках браузера')
      } else if (err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError') {
        setError('Микрофон не найден')
      } else if (!navigator.mediaDevices) {
        setError('Браузер не поддерживает запись (нужен HTTPS)')
      } else {
        setError(`Ошибка микрофона: ${err?.name || 'неизвестно'}`)
      }
    }
  }, [onTranscription])

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    }
    setRecording(false)
  }, [])

  const toggle = useCallback(() => {
    if (recording) stop()
    else start()
  }, [recording, start, stop])

  return { recording, processing, error, toggle }
}
