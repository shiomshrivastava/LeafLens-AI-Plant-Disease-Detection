import type { Report } from './AnalysisPanel';
import type { Language } from './i18n';

/** Only user-friendly interpretations are shown; internal diagnostic text stays in the backend. */
export function publicResultMessage(report: Report, language: Language): string {
  const messages: Record<string, [string, string]> = {
    HEALTHY: [
      'This leaf appears healthy in the photo. Continue regular care and keep an eye out for any changes.',
      'इस फोटो में पत्ता स्वस्थ दिखाई दे रहा है। नियमित देखभाल करें और समय-समय पर बदलावों पर ध्यान दें।',
    ],
    DISEASED_ANALYSIS_COMPLETE: [
      'Possible signs of disease were found. Review the highlighted areas and care tips before taking action.',
      'पत्ते में रोग के संभावित लक्षण दिखे हैं। कोई कदम उठाने से पहले प्रभावित हिस्से और देखभाल के सुझाव देखें।',
    ],
    REVIEW_CROP_DISAGREEMENT: [
      'The crop could not be identified reliably. Please confirm the crop before deciding on treatment.',
      'फसल की पहचान स्पष्ट नहीं है। उपचार चुनने से पहले फसल की पुष्टि करें।',
    ],
    RETAKE_IMAGE: [
      'This photo is difficult to assess. Please take another clear photo in good lighting.',
      'इस फोटो से सही जानकारी मिलना मुश्किल है। अच्छी रोशनी में एक साफ फोटो दोबारा लें।',
    ],
    NOT_USABLE_LEAF: [
      'A clear leaf could not be identified. Try a closer photo showing one whole leaf.',
      'इस फोटो में पत्ता साफ दिखाई नहीं दे रहा। पूरे पत्ते की नज़दीक से फोटो लें।',
    ],
    CROP_NOT_VERIFIED: [
      'This crop could not be confirmed. Check the supported crop list and try another clear photo.',
      'इस फसल की पहचान की पुष्टि नहीं हुई। समर्थित फसलों की सूची देखकर साफ फोटो दोबारा लें।',
    ],
  };
  const pair = messages[report.decision];
  return pair ? pair[language === 'hi' ? 1 : 0] : language === 'hi'
    ? 'इस फोटो की जाँच पूरी नहीं हो सकी। कृपया दूसरे साफ फोटो से कोशिश करें।'
    : 'This photo could not be assessed. Please try another clear leaf photo.';
}

export function publicResultLabel(report: Report): string {
  const labels: Record<string, string> = {
    HEALTHY: 'Healthy leaf',
    DISEASED_ANALYSIS_COMPLETE: 'Possible disease',
    REVIEW_CROP_DISAGREEMENT: 'Crop needs review',
    RETAKE_IMAGE: 'Retake photo',
    NOT_USABLE_LEAF: 'Leaf not clear',
    CROP_NOT_VERIFIED: 'Crop not confirmed',
  };
  return labels[report.decision] || 'Review needed';
}
