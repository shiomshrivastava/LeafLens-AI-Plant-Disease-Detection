import { useEffect, useRef, useState } from 'react';
import { Camera, CircleAlert, X } from 'lucide-react';
import { t } from './i18n';
import type { Language } from './i18n';

/** The camera is started only on user request; every stream track is stopped on exit. */
export function CameraCapture({ onCapture, language, disabled }: {
  onCapture: (file: File) => void; language: Language; disabled?: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const media = useRef<MediaStream | null>(null);
  const live = useRef(true);
  const [opened, setOpened] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');

  function stop() {
    live.current = false;
    media.current?.getTracks().forEach(track => track.stop());
    media.current = null;
    if (video.current) video.current.srcObject = null;
    setOpened(false); setStarting(false);
  }
  useEffect(() => () => {
    live.current = false;
    media.current?.getTracks().forEach(track => track.stop());
  }, []);
  useEffect(() => {
    if (!opened || !video.current || !media.current) return;
    video.current.srcObject = media.current;
    void video.current.play().catch(() => setError('Could not play the camera preview.'));
  }, [opened]);
  async function start() {
    setError(''); setStarting(true); live.current = true;
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Camera access requires localhost or a secure HTTPS connection.');
      setStarting(false); return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 960 } },
      });
      if (!live.current) { stream.getTracks().forEach(track => track.stop()); return; }
      media.current = stream;
      setOpened(true);
      // React's opened state mounts <video>; the effect above attaches stream.
    } catch (err: unknown) {
      const reason = err instanceof Error ? err.name : '';
      setError(reason === 'NotAllowedError'
        ? 'Camera permission was denied. Allow access in your browser settings.'
        : reason === 'NotFoundError' ? 'No camera was found on this device.' : 'Camera could not be opened.');
    } finally { if (live.current) setStarting(false); }
  }
  function capture() {
    const v = video.current;
    if (!v || !v.videoWidth || !v.videoHeight) { setError('Camera is not ready yet.'); return; }
    const canvas = document.createElement('canvas');
    canvas.width = v.videoWidth; canvas.height = v.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) { setError('Could not capture the photo.'); return; }
    ctx.drawImage(v, 0, 0);
    canvas.toBlob(blob => {
      if (!live.current) return;
      if (!blob) { setError('Could not encode the captured photo.'); return; }
      onCapture(new File([blob], `LeafLens_camera_${Date.now()}.jpg`, { type: 'image/jpeg' }));
      stop();
    }, 'image/jpeg', 0.9);
  }
  return <div className="camera-control">
    {!opened && <button type="button" className="secondary-action" disabled={starting || disabled} onClick={() => void start()}>
      <Camera size={18} />{starting ? 'Opening…' : t(language, 'Open Camera')}
    </button>}
    {opened && <div className="camera-live">
      <div className="camera-video-frame"><video ref={video} autoPlay muted playsInline aria-label="Live camera preview" /></div>
      <div className="camera-actions">
        <button type="button" className="primary-action" onClick={capture}><Camera size={17} />{t(language, 'Capture Photo')}</button>
        <button type="button" className="secondary-action" onClick={stop}><X size={17} />{t(language, 'Close Camera')}</button>
      </div>
    </div>}
    {error && <p className="inline-error" role="alert"><CircleAlert size={16} />{error}</p>}
  </div>;
}
