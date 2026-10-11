import { useMemo, useState } from 'react';
import { Search, Sprout, Camera } from 'lucide-react';
import { t } from './i18n';
import type { Language } from './i18n';

// Supported crops come from the 15-class Model-0C training specification.
const crops = [
  ['Apple', 'सेब'], ['Bell Pepper', 'शिमला मिर्च'], ['Blueberry', 'ब्लूबेरी'],
  ['Cauliflower', 'फूलगोभी'], ['Corn', 'मक्का'], ['Eggplant', 'बैंगन'],
  ['Grape', 'अंगूर'], ['Peach', 'आड़ू'], ['Potato', 'आलू'],
  ['Raspberry', 'रास्पबेरी'], ['Rice', 'धान'], ['Soybean', 'सोयाबीन'],
  ['Strawberry', 'स्ट्रॉबेरी'], ['Tomato', 'टमाटर'], ['Wheat', 'गेहूँ'],
] as const;

export function CropsLibrary({ language }: { language: Language }) {
  const [query, setQuery] = useState('');
  const shown = useMemo(() => crops.filter(([en, hi]) => `${en} ${hi}`.toLowerCase().includes(query.trim().toLowerCase())), [query]);
  return <section className="secondary-page crops-page">
    <div className="page-heading"><h1>{t(language, 'Supported Crop Library')}</h1><p>{language === 'hi' ? 'ये 15 फसलें हमारे crop classification model में शामिल हैं।' : 'These are the 15 crops represented in our crop identification model.'}</p></div>
    <div className="card crops-intro"><div><Sprout size={25}/><strong>{t(language,'15 supported crops')}</strong></div><p>{language === 'hi' ? 'समर्थित फसल की पहचान भी अनुमान है; अनजान फसलों को कभी-कभी गलती से स्वीकार किया जा सकता है।' : 'Support refers to training coverage, not a guarantee of correct identification. Unfamiliar crops may occasionally be accepted incorrectly.'}</p></div>
    <label className="crop-search"><Search size={19}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder={t(language,'Search crops')} aria-label={t(language,'Search crops')}/></label>
    <div className="crops-grid">{shown.map(([en, hi]) => <article className="card crop-tile" key={en}><span className="crop-tile-mark"><Sprout size={26}/></span><div><h2>{en}</h2><p>{hi}</p></div><span className="crop-supported">{language === 'hi' ? 'समर्थित' : 'Supported'}</span></article>)}</div>
    {!shown.length && <p className="crop-no-results">{language === 'hi' ? 'इस नाम से कोई फसल नहीं मिली।' : 'No supported crops match this search.'}</p>}
    <div className="card crop-photo-tips"><Camera size={24}/><div><h2>{t(language,'Tips for a better image')}</h2><p>{language === 'hi' ? 'एक स्पष्ट पत्ता, पर्याप्त रोशनी और साधारण बैकग्राउंड का उपयोग करें। पूरी पत्ती फ़्रेम में रखें।' : 'Photograph one leaf in good natural light, with a simple background. Keep the whole leaf in focus and inside the frame.'}</p></div></div>
  </section>;
}
