import { useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import type { Language } from './i18n';
import { t } from './i18n';

export function SegmentationViewer({ original, overlay, language }: { original: string; overlay: string; language: Language }) {
  const [position, setPosition] = useState(50);
  const [opacity, setOpacity] = useState(100);
  const dragPointer = useRef<number | null>(null);

  function moveDivider(event: ReactPointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    const fraction = (event.clientX - rect.left) / rect.width;
    setPosition(Math.round(Math.max(0, Math.min(1, fraction)) * 100));
  }
  function beginDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    dragPointer.current = event.pointerId;
    event.currentTarget.setPointerCapture(event.pointerId);
    moveDivider(event);
  }
  function continueDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragPointer.current === event.pointerId) moveDivider(event);
  }
  function endDrag(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragPointer.current !== event.pointerId) return;
    moveDivider(event);
    dragPointer.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }
  function keyboardMove(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      setPosition(current => Math.max(0, Math.min(100, current + (event.key === 'ArrowLeft' ? -5 : 5))));
    }
    if (event.key === 'Home') { event.preventDefault(); setPosition(0); }
    if (event.key === 'End') { event.preventDefault(); setPosition(100); }
  }

  return <section className="card compare-card" aria-label={t(language,'Interactive Segmentation Viewer')}>
    <div className="compare-title"><SlidersHorizontal size={20}/><h2>{t(language,'Interactive Segmentation Viewer')}</h2></div>
    <div className="compare-canvas" onPointerDown={beginDrag} onPointerMove={continueDrag} onPointerUp={endDrag} onPointerCancel={endDrag}>
      <img className="compare-layer" src={original} alt={t(language,'Original image')} draggable={false}/>
      <div className="compare-overlay-window" style={{ clipPath: `inset(0 ${100-position}% 0 0)` }}>
        <img className="compare-layer" src={overlay} alt={t(language,'Disease overlay')} style={{opacity:opacity/100}} draggable={false}/>
      </div>
      <button type="button" className="compare-divider" style={{left:`${position}%`}}
        aria-label={language === 'hi' ? 'दो तस्वीरों की तुलना करें; बाएँ या दाएँ खींचें' : 'Compare photos; drag left or right'}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={position} role="slider"
        onKeyDown={keyboardMove}><span aria-hidden="true">↔</span></button>
      <span className="compare-label compare-label-left">{t(language,'Disease overlay')}</span>
      <span className="compare-label compare-label-right">{t(language,'Original image')}</span>
    </div>
    <div className="compare-controls">
      <label>{t(language,'Before / after')} <strong>{position}%</strong>
        <input type="range" min="0" max="100" step="1" value={position} onChange={e => setPosition(Number(e.target.value))}/>
      </label>
      <label>{t(language,'Overlay opacity')} <strong>{opacity}%</strong>
        <input type="range" min="0" max="100" step="1" value={opacity} onChange={e => setOpacity(Number(e.target.value))}/>
      </label>
    </div>
    <p className="compare-note">{language === 'hi' ? 'तस्वीर के बीच वाले बटन को बाएँ-दाएँ खींचें या नीचे स्लाइडर से तुलना करें।' : 'Drag the middle handle left or right to compare images, or use the slider below.'}</p>
  </section>;
}
