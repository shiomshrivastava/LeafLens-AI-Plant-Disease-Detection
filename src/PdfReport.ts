import { jsPDF } from 'jspdf';
import type { AnalysisEntry } from './AnalysisPanel';
import { publicResultLabel, publicResultMessage } from './resultCopy';

/** Make a real A4 PDF locally. No client-side service key or remote PDF service. */
const clean = (value: unknown) => String(value ?? 'Not assessed').replace(/[\u0000-\u001f]/g, ' ').trim();
const percent = (value: number | undefined) => typeof value === 'number' && Number.isFinite(value)
  ? `${value.toFixed(2)}%` : 'Not assessed';

async function pdfImage(source: string): Promise<{ data: string; ratio: number } | null> {
  try {
    const response = await fetch(source, { mode: 'cors' });
    if (!response.ok) return null;
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);
    const maxSize = 1100;
    const scale = Math.min(1, maxSize / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) { bitmap.close(); return null; }
    context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const ratio = canvas.width / canvas.height;
    bitmap.close();
    return { data: canvas.toDataURL('image/jpeg', 0.84), ratio };
  } catch { return null; }
}

export async function downloadAnalysisPdf(entry: AnalysisEntry): Promise<{ imagesSkipped: boolean }> {
  const doc = new jsPDF({ format: 'a4', unit: 'mm', compress: true });
  const report = entry.report;
  const date = new Date(entry.date).toLocaleString('en-IN');
  const crop = clean(report.model0c?.predicted_crop || report.model2?.crop || 'Not verified');
  const disease = report.model1?.status === 'HEALTHY'
    ? 'No disease predicted' : clean(report.model2?.disease || 'Not assessed');
  const severity = clean(report.model3?.severity);
  const write = (text: string, y: number, fontSize = 10, color: [number,number,number] = [33, 49, 44]) => {
    doc.setFont('helvetica','normal'); doc.setFontSize(fontSize); doc.setTextColor(...color);
    const lines = doc.splitTextToSize(text, 175);
    doc.text(lines, 18, y);
    return y + lines.length * (fontSize * 0.47) + 3;
  };
  doc.setFillColor(7, 92, 57); doc.rect(0,0,210,31,'F');
  doc.setFont('helvetica','bold'); doc.setTextColor(255,255,255); doc.setFontSize(22);
  doc.text('LeafLens',18,15); doc.setFontSize(10); doc.text('PLANT HEALTH ANALYSIS',18,23);
  let y = 41;
  y = write(`Report date: ${date}`, y);
  y = write(`Image: ${clean(entry.fileName).slice(0,120)}`,y);
  doc.setDrawColor(209,226,213); doc.line(18,y,192,y); y+=8;
  const summary = [
    ['Result', publicResultLabel(report)],
    ['Crop', crop],
    ['Health status', clean(report.model1?.status)],
    ['Predicted disease', disease],
    ['Prediction confidence', report.model2 ? percent(report.model2.confidence * 100) : 'Not assessed'],
    ['Severity category', severity],
    ['Affected image area', percent(report.model3?.affected_percent)],
  ];
  for (const [key,value] of summary) {
    doc.setFont('helvetica','bold'); doc.setFontSize(10); doc.setTextColor(21,75,51);
    doc.text(`${key}:`,18,y); y = write(value,y+5,10); y+=1;
  }
  if (y > 246) { doc.addPage(); y = 19; }
  doc.setFont('helvetica','bold'); doc.setFontSize(12); doc.setTextColor(7,92,57);
  doc.text('Interpretation', 18, y); y+=7;
  y = write(publicResultMessage(report, 'en'),y,9);
  if (report.model2 && report.model2.confidence < 0.5) {
    y = write('CAUTION: The disease prediction is uncertain. Confirm symptoms before treatment.',y,9,[153,90,19]);
  }
  if (report.crop_agreement?.agree === false) {
    y = write('CAUTION: Crop identification is uncertain. Please confirm the crop.',y,9,[153,90,19]);
  }
  // Saved care advice is part of each analysis, so exports from
  // both fresh Results and reopened History contain the exact same advice.
  const care = report.recommendations;
  if (care) {
    doc.addPage(); y = 20;
    doc.setFont('helvetica', 'bold'); doc.setFontSize(16); doc.setTextColor(7, 92, 57);
    doc.text('Plant Health Recommendations', 18, y); y += 10;
    doc.setFont('helvetica', 'normal');
    y = write(clean(care.title_en), y, 12);
    for (let i = 0; i < care.tips_en.length; i++) {
      if (y > 256) { doc.addPage(); y = 22; }
      y = write(`${i + 1}. ${clean(care.tips_en[i])}`, y + 3, 10);
    }
    if (y > 243) { doc.addPage(); y = 22; }
    y = write(`Important: ${clean(care.disclaimer_en)}`, y + 9, 9, [137, 93, 41]);
  }
  const images = [
    { title:'Original leaf image', source:entry.imageUrl },
    { title:'Diseased-region overlay', source:report.overlay_image },
    { title:'Predicted lesion mask', source:report.mask_image },
  ];
  let skipped = false;
  doc.addPage(); y=19;
  doc.setFont('helvetica','bold'); doc.setTextColor(7,92,57); doc.setFontSize(16);
  doc.text('Image evidence',18,y); y+=9;
  for (const item of images) {
    if (!item.source) continue;
    const img = await pdfImage(item.source);
    if (!img) { skipped = true; y = write(`${item.title}: image unavailable (expired URL or browser CORS restriction).`,y); continue; }
    const w = Math.min(165, 96 * img.ratio); const h = w / img.ratio;
    if (y+h+14>272) { doc.addPage(); y=20; }
    doc.setFont('helvetica','bold'); doc.setFontSize(11); doc.setTextColor(23,73,47);
    doc.text(item.title,18,y); y+=5;
    doc.addImage(img.data,'JPEG',18,y,w,h,undefined,'FAST'); y+=h+12;
  }
  if (y+40>272) { doc.addPage(); y=20; }
  doc.setFont('helvetica','bold'); doc.setFontSize(10); doc.setTextColor(112,91,66);
  doc.text('IMPORTANT LIMITATIONS',18,y); y+=6;
  y=write('These results are for initial guidance, not a confirmed diagnosis. Confirm symptoms before treatment.',y,8);
  write('Affected-area percentage is measured over the full image, not only the leaf area.',y,8);
  doc.save(`LeafLens_${new Date(entry.date).toISOString().slice(0,10)}_${entry.id.slice(0,8)}.pdf`);
  return { imagesSkipped: skipped };
}
