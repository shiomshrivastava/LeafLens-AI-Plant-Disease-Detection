import { useState } from 'react';
import { AlertCircle, AlertTriangle, ArrowLeft, CheckCircle2, CircleHelp, Download, Leaf, ShieldAlert, Sprout } from 'lucide-react';
import type { Language } from './i18n';
import { t } from './i18n';
import { downloadAnalysisPdf } from './PdfReport';
import { SegmentationViewer } from './SegmentationViewer';
import { QualityGuidance } from './QualityGuidance';
import { publicResultMessage } from './resultCopy';

export type Stage = { id: string; status: string; detail: string };
export type CareRecommendations = {
  module: string;
  method: 'rule_based';
  status: 'healthy' | 'retake' | 'review' | 'general' | 'disease_guidance';
  rule_id: string;
  title_en: string;
  title_hi: string;
  tips_en: string[];
  tips_hi: string[];
  disclaimer_en: string;
  disclaimer_hi: string;
  based_on?: { crop?: string | null; disease?: string | null; severity?: string | null; disease_confidence?: number | null };
};

export type Report = {
  decision: string;
  message: string;
  explanation: string;
  stage_summary: Stage[];
  model0a?: { accepted: boolean; reasons?: string[] } | null;
  model0b?: { confidence: number } | null;
  model0c?: { predicted_crop: string; top_crop_guess?: string } | null;
  model1?: { status: string; diseased_probability: number } | null;
  model2?: {
    crop: string; disease: string; confidence: number;
    top3: { crop: string; disease: string; confidence: number }[];
  } | null;
  model3?: { affected_percent: number; severity: string } | null;
  crop_agreement?: { agree: boolean } | null;
  overlay_image?: string | null;
  mask_image?: string | null;
  severity_basis?: string;
  saved_analysis_id?: string | null;
  history_warning?: string | null;
  recommendations?: CareRecommendations | null;
};

export type AnalysisEntry = {
  id: string;
  fileName: string;
  imageUrl: string;
  date: number;
  report: Report;
};

const friendlyStatus: Record<string, { label: string; tone: 'good' | 'warn' | 'bad' }> = {
  HEALTHY: { label: 'Healthy leaf', tone: 'good' },
  DISEASED_ANALYSIS_COMPLETE: { label: 'Disease detected', tone: 'warn' },
  REVIEW_CROP_DISAGREEMENT: { label: 'Crop identification needs review', tone: 'warn' },
  RETAKE_IMAGE: { label: 'Photo needs retaking', tone: 'bad' },
  NOT_USABLE_LEAF: { label: 'Not a usable leaf', tone: 'bad' },
  CROP_NOT_VERIFIED: { label: 'Crop not verified', tone: 'bad' },
};
function fmt(n: number | undefined, places = 1) {
  return typeof n === 'number' && Number.isFinite(n) ? n.toFixed(places) : '—';
}

export function AnalysisPanel({ entry, onBack, language }: { entry: AnalysisEntry; onBack: () => void; language: Language }) {
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const result = entry.report;
  const status = friendlyStatus[result.decision] ?? { label: 'Review needed', tone: 'warn' as const };
  const crop = result.model0c?.predicted_crop && result.model0c.predicted_crop !== 'UNKNOWN'
    ? result.model0c.predicted_crop : t(language, 'Not verified');
  const condition = result.model1?.status === 'HEALTHY' ? t(language, 'Healthy') : result.model1?.status === 'DISEASED' ? t(language, 'Diseased') : t(language, 'Not assessed');
  const severity = result.model3?.severity ?? 'Not assessed';
  const date = new Date(entry.date).toLocaleString(language === 'hi' ? 'hi-IN' : undefined, { dateStyle: 'medium', timeStyle: 'short' });
  const lowConfidence = result.model2 && result.model2.confidence < .5;

  async function exportPdf() {
    if (pdfBusy) return;
    setPdfBusy(true); setPdfError('');
    try {
      const { imagesSkipped } = await downloadAnalysisPdf(entry);
      if (imagesSkipped) setPdfError(language === 'hi'
        ? 'PDF बन गई, लेकिन कुछ तस्वीरें नहीं जुड़ सकीं। पुरानी signed URL एक्सपायर हो सकती है।'
        : 'PDF downloaded, but some images were unavailable. Reopen the saved analysis to refresh its signed URLs.');
    } catch (err: unknown) {
      setPdfError(err instanceof Error ? err.message : 'Could not create PDF report.');
    } finally { setPdfBusy(false); }
  }
  return <div className="results-page">
    <div className="page-heading results-heading">
      <div>
        <button type="button" className="back-link" onClick={onBack}><ArrowLeft size={17} />{t(language, 'Back to Home')}</button>
        <h1>{t(language, 'Analysis Results')}</h1>
        <p>{language === 'hi' ? 'आपकी पत्ती की तस्वीर के लिए AI आधारित जानकारी।' : 'AI-powered insights for your uploaded leaf image.'}</p>
      </div>
      <div className="results-tools"><time>{date}</time><button type="button" className="outline-button" disabled={pdfBusy} onClick={() => void exportPdf()}><Download size={16} />{pdfBusy ? t(language, 'Preparing PDF…') : t(language, 'Download PDF')}</button></div>
    </div>
    {pdfError && <p className="analysis-caution" role="status">{pdfError}</p>}
    <section className="results-overview card" aria-label="Leaf analysis summary">
      <div className="overview-thumb"><img src={entry.imageUrl} alt="Uploaded leaf" /></div>
      <div className="overview-stat"><span>{t(language, 'Crop')}</span><strong>{crop}</strong></div>
      <div className="overview-stat"><span>{t(language, 'Health status')}</span><strong><span className={`mini-status ${result.model1?.status === 'HEALTHY' ? 'mini-good' : result.model1?.status === 'DISEASED' ? 'mini-danger' : 'mini-neutral'}`}>{condition}</span></strong></div>
      <div className="overview-stat"><span>{t(language, 'Predicted disease')}</span><strong>{result.model2?.disease ?? t(language, 'Not assessed')}</strong></div>
      <div className="overview-stat"><span>{t(language, 'Severity')}</span><strong><span className={`mini-status severity-${severity.toLowerCase()}`}>{severity}</span></strong></div>
      <div className="overview-stat"><span>{t(language, 'Mask coverage')}</span><strong>{result.model3 ? `${fmt(result.model3.affected_percent, 2)}%` : t(language, 'Not assessed')}</strong></div>
    </section>
    <div className={`result-message message-${status.tone}`}>
      {status.tone === 'good' ? <CheckCircle2 size={20} /> : status.tone === 'bad' ? <ShieldAlert size={20} /> : <AlertTriangle size={20} />}
      <div><strong>{t(language, status.label)}</strong><p>{publicResultMessage(result, language)}</p></div>
    </div>
    {result.history_warning && <p className="analysis-caution" role="alert"><CircleHelp size={17} />{result.history_warning}</p>}
    {(result.model2 && lowConfidence) && <p className="analysis-caution"><CircleHelp size={17} />{language === 'hi' ? `रोग की पहचान अभी अनिश्चित है (${fmt(result.model2.confidence * 100)}% भरोसा)। इलाज से पहले लक्षणों की पुष्टि करें।` : `The disease prediction is uncertain (${fmt(result.model2.confidence * 100)}% confidence). Please confirm the symptoms before treatment.`}</p>}
    {result.crop_agreement && !result.crop_agreement.agree && <p className="analysis-caution"><AlertTriangle size={17} />{language === 'hi' ? 'फसल की पहचान स्पष्ट नहीं है। कोई इलाज चुनने से पहले फसल की पुष्टि करें।' : 'The crop identification is uncertain. Please confirm the crop before choosing treatment.'}</p>}

    {result.recommendations && <section className="card care-recommendation" aria-label="Plant health recommendations">
      <div className="care-recommendation-heading"><span className="care-recommendation-icon"><Sprout size={20} /></span>
        <div><span className="care-recommendation-kicker">{t(language, 'Plant Care Recommendations')}</span>
          <h2>{language === 'hi' ? result.recommendations.title_hi : result.recommendations.title_en}</h2>
        </div>
      </div>
      <ol className="care-recommendation-list">
        {(language === 'hi' ? result.recommendations.tips_hi : result.recommendations.tips_en).map((tip, i) => <li key={`${i}-${tip}`}>{tip}</li>)}
      </ol>
      <p className="care-recommendation-disclaimer">{language === 'hi' ? result.recommendations.disclaimer_hi : result.recommendations.disclaimer_en}</p>
    </section>}
    {result.overlay_image && <SegmentationViewer original={entry.imageUrl} overlay={result.overlay_image} language={language} />}
    <div className="results-content-grid">
      <section className="card evidence-card">
        <h2>{result.overlay_image ? t(language, 'Disease overlay') : t(language, 'Original image')}</h2>
        <div className="evidence-picture"><img src={result.overlay_image || entry.imageUrl} alt={result.overlay_image ? 'Disease regions highlighted over the original photograph' : 'Uploaded image'} /></div>
        <p>{result.overlay_image ? (language === 'hi' ? 'नारंगी रंग अनुमानित प्रभावित हिस्से दिखाता है।' : 'Orange highlights mark regions estimated as diseased.') : (language === 'hi' ? 'इस छवि के लिए ओवरले नहीं बना।' : 'No disease-region overlay was generated for this image.')}</p>
      </section>
      <section className="card evidence-card">
        <h2>{t(language, 'Predicted segmentation mask')}</h2>
        <div className="evidence-picture mask-background">{result.mask_image ? <img src={result.mask_image} alt="Predicted lesion mask" /> : <div className="no-mask"><Leaf size={35} /><span>{t(language, 'Mask not generated')}</span></div>}</div>
        <p>{result.mask_image ? (language === 'hi' ? 'सफ़ेद हिस्से अनुमानित रोगग्रस्त क्षेत्र हैं।' : 'White pixels show predicted affected regions.') : (language === 'hi' ? 'इस फोटो के लिए प्रभावित क्षेत्र नहीं दिखाया जा सका।' : 'Affected areas are not available for this photo.')}</p>
      </section>
    </div>
    <QualityGuidance report={result} language={language} />
    <div className="disclaimer"><AlertCircle size={18} /><p><strong>{language === 'hi' ? 'ध्यान दें:' : 'Please note:'}</strong> {language === 'hi' ? 'यह परिणाम केवल शुरुआती जानकारी के लिए है, निश्चित निदान नहीं। प्रभावित क्षेत्र का प्रतिशत पूरी फोटो के आधार पर है, केवल पत्ते के हिस्से पर नहीं। किसी भी उपचार से पहले लक्षणों की पुष्टि करें।' : 'These results offer initial guidance, not a confirmed diagnosis. The affected-area percentage is based on the full image, not just the leaf. Confirm the symptoms before choosing treatment.'}</p></div>
  </div>;
}
