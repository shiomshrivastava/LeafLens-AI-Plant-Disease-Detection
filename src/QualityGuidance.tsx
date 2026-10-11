import { Lightbulb, Camera, CircleHelp } from 'lucide-react';
import { t } from './i18n';
import type { Language } from './i18n';
import type { Report } from './AnalysisPanel';

const reasonGuidance: Record<string, string> = {
  LOW_RESOLUTION: 'Choose a higher-resolution photograph.',
  BLUR_LOCAL_TOP25: 'Keep the leaf sharp and steady; avoid motion blur.',
  TOO_FEW_SHARP_TILES: 'Keep the leaf sharp and steady; avoid motion blur.',
  TOO_DARK: 'Use bright, even daylight without harsh shadows.',
  TOO_BRIGHT: 'Avoid very bright or washed-out photographs.',
  TOO_MANY_DARK_PIXELS: 'Use bright, even daylight without harsh shadows.',
  TOO_MANY_BRIGHT_PIXELS: 'Avoid very bright or washed-out photographs.',
  LOW_CONTRAST: 'Use a photo with better contrast and clear leaf details.',
};
const normalTips = [
  'Fill most of the photo with one clearly visible leaf.',
  'Use bright, even daylight without harsh shadows.',
  'Keep the entire leaf visible against a simple background.',
  'Keep the leaf sharp and steady; avoid motion blur.',
];
export function QualityGuidance({ report, language }: { report?: Report; language: Language }) {
  const problems = report?.model0a?.reasons ?? [];
  const tips = problems.length
    ? Array.from(new Set(problems.map(code => reasonGuidance[code]).filter(Boolean)))
    : report?.decision === 'NOT_USABLE_LEAF'
      ? ['Fill most of the photo with one clearly visible leaf.', 'Keep the entire leaf visible against a simple background.']
      : report?.decision === 'CROP_NOT_VERIFIED'
        ? ['Photograph a supported crop (see the crop library).', 'No separate diagnosis is shown when crop support is uncertain.']
        : normalTips;
  return <section className="quality-guidance" aria-label={t(language,'Image Quality Guidance')}>
    <div className="quality-head"><Lightbulb size={20}/><h2>{t(language,'Image Quality Guidance')}</h2></div>
    {report?.decision === 'RETAKE_IMAGE' && <p className="quality-flag"><CircleHelp size={16}/>{language === 'hi' ? 'गुणवत्ता जाँच में समस्या पाई गई। दोबारा फोटो लें।' : 'This photo is difficult to assess. Please take a clearer, well-lit photo.'}</p>}
    <div className="quality-tips">{tips.map(tip => <div key={tip}><Camera size={15}/><span>{t(language,tip)}</span></div>)}</div>
  </section>;
}
