"""LeafLens Model-4: explainable, rule-based plant-care guidance (NO trained model).

Uses only the validated final decision, predicted disease, disease confidence,
and segmentation-derived severity. No additional internet or external service.
These are conservative, non-chemical care suggestions; never a diagnosis.
"""
from __future__ import annotations

import re
from typing import Any

RULES: tuple[tuple[str, tuple[str, ...], tuple[str, str, str], tuple[str, str, str]], ...] = (
    (
        'late_blight', ('late blight',),
        ('Late blight spreads readily in damp conditions: water at soil level and keep leaves dry.',
         'If blight-like lesions are confirmed, carefully remove affected leaves, dispose of them away from the garden, and clean tools.',
         'Check nearby tomato plants for fast-spreading dark or water-soaked patches.'),
        ('नम वातावरण में लेट ब्लाइट तेजी से फैल सकता है: मिट्टी के पास पानी दें और पत्तियाँ सूखी रखें।',
         'धब्बों की पुष्टि होने पर प्रभावित पत्तियाँ सावधानी से हटाएँ, बगीचे से दूर निपटाएँ और औज़ार साफ़ करें।',
         'आसपास के टमाटर के पौधों में तेजी से फैलते गहरे या पानी जैसे धब्बे देखें।'),
    ),
    (
        'powdery_mildew', ('powdery mildew',),
        ('Improve air circulation around crowded foliage.',
         'Avoid splashing leaves when watering.',
         'Monitor new leaves for white powdery patches.'),
        ('घनी पत्तियों के आसपास हवा का प्रवाह बढ़ाएँ।',
         'पानी देते समय पत्तियों पर छींटे पड़ने से बचाएँ।',
         'नई पत्तियों पर सफेद पाउडर जैसे धब्बों को देखें।'),
    ),
    (
        'downy_mildew', ('downy mildew',),
        ('Reduce prolonged leaf wetness and improve ventilation.',
         'Water near the soil instead of wetting the foliage.',
         'Inspect the underside of nearby leaves for similar symptoms.'),
        ('पत्तियों को लंबे समय तक गीला न रहने दें और हवा आने दें।',
         'पत्तियों की जगह मिट्टी के पास पानी दें।',
         'आसपास की पत्तियों के नीचे भी ऐसे लक्षण देखें।'),
    ),
    (
        'virus', ('virus', 'viral', 'mosaic', 'leaf curl', 'yellow curl', 'yellowing curl'),
        ('Do not reuse tools between symptomatic and healthy plants without cleaning.',
         'Check nearby plants and look for insects that may spread disease.',
         'Ask a local agriculture expert before removing or treating plants.'),
        ('लक्षण वाले और स्वस्थ पौधों के बीच औज़ार इस्तेमाल करने से पहले साफ़ करें।',
         'आसपास के पौधों और रोग फैला सकने वाले कीड़ों की जाँच करें।',
         'पौधे को हटाने या उपचार से पहले स्थानीय कृषि विशेषज्ञ से सलाह लें।'),
    ),
    (
        'bacterial', ('bacterial', 'bacterium', 'canker', 'fire blight'),
        ('Avoid handling foliage while it is wet.',
         'Disinfect tools after inspecting or pruning affected plants.',
         'Avoid splashing water between neighboring plants.'),
        ('गीली पत्तियों को छूने या संभालने से बचें।',
         'प्रभावित पौधों को देखने या काटने के बाद औज़ार साफ़ करें।',
         'पानी के छींटे एक पौधे से दूसरे पौधे तक जाने से रोकें।'),
    ),
    (
        'rust', ('rust',),
        ('Improve airflow and reduce leaf wetness.',
         'Avoid watering directly onto leaves.',
         'Look for orange or brown spots on neighboring leaves.'),
        ('हवा का प्रवाह बढ़ाएँ और पत्तियों को ज्यादा गीला न रहने दें।',
         'सीधे पत्तियों पर पानी डालने से बचें।',
         'आसपास की पत्तियों पर नारंगी या भूरे धब्बे देखें।'),
    ),
    (
        'leaf_spot_blight', ('early blight', 'leaf spot', 'septoria', 'cercospora',
                             'alternaria', 'target spot', 'anthracnose', 'scab',
                             'gray leaf', 'grey leaf', 'leaf blight', 'black spot'),
        ('Avoid overhead watering; water close to the soil.',
         'Remove fallen, heavily affected leaves where practical and clean tools.',
         'Allow more space and airflow around leaves.'),
        ('ऊपर से पानी न डालें; मिट्टी के पास पानी दें।',
         'जहाँ संभव हो, गिरे हुए बहुत प्रभावित पत्ते हटाएँ और औज़ार साफ़ करें।',
         'पत्तियों के आसपास जगह और हवा का प्रवाह बढ़ाएँ।'),
    ),
    (
        'rot', ('rot', 'wilt', 'damping off'),
        ('Check whether soil is waterlogged and improve drainage if needed.',
         'Avoid unnecessary watering until the soil condition is checked.',
         'Keep tools clean and examine nearby plants for similar symptoms.'),
        ('मिट्टी में पानी भरने की स्थिति जाँचें और जरूरत पर जल निकासी सुधारें।',
         'मिट्टी की स्थिति जाँचे बिना अतिरिक्त पानी देने से बचें।',
         'औज़ार साफ़ रखें और आसपास के पौधों में ऐसे लक्षण देखें।'),
    ),
    (
        'pest', ('mite', 'spider mite', 'aphid', 'insect', 'miner', 'thrips', 'pest'),
        ('Inspect both sides of leaves for insects or feeding damage.',
         'Keep affected foliage under observation and limit pest transfer.',
         'Seek locally appropriate pest identification before any treatment.'),
        ('पत्तियों के दोनों तरफ कीड़े या खाने से हुए नुकसान देखें।',
         'प्रभावित पत्तियों को देखते रहें और कीड़ों को फैलने से रोकें।',
         'उपचार से पहले स्थानीय स्तर पर कीट की पहचान कराएँ।'),
    ),
)

BASE_TIPS_EN = (
    'Avoid wetting foliage unnecessarily and provide good air circulation.',
    'Inspect the plant and nearby leaves for changes over the next few days.',
    'Keep gardening tools clean between plants.',
)
BASE_TIPS_HI = (
    'बिना जरूरत पत्तियों को गीला न करें और हवा का अच्छा प्रवाह रखें।',
    'अगले कुछ दिनों तक पौधे और आसपास की पत्तियाँ जाँचते रहें।',
    'अलग-अलग पौधों पर काम करते समय औज़ार साफ़ रखें।',
)
DISCLAIMER_EN = ('General preventive guidance based on AI predictions, not a confirmed diagnosis '
                 'or a prescription. Consult local agricultural guidance before using any pesticide.')
DISCLAIMER_HI = ('यह AI अनुमान पर आधारित सामान्य देखभाल की सलाह है, पक्का निदान या दवा का निर्देश नहीं। '
                 'किसी भी कीटनाशक के उपयोग से पहले स्थानीय कृषि विशेषज्ञ की सलाह लें।')


def _text(value: Any) -> str:
    return re.sub(r'\s+', ' ', str(value or '').replace('_', ' ').replace('-', ' ')).strip()


def _payload(status: str, rule_id: str, title_en: str, title_hi: str,
             tips_en: tuple[str, ...], tips_hi: tuple[str, ...],
             *, crop: str, disease: str, severity: str, confidence: float | None) -> dict:
    return {
        'module': 'Model-4: Rule-Based Plant Health Recommendations',
        'version': 2,
        'method': 'rule_based',
        'status': status,
        'rule_id': rule_id,
        'title_en': title_en,
        'title_hi': title_hi,
        'tips_en': list(tips_en),
        'tips_hi': list(tips_hi),
        'disclaimer_en': DISCLAIMER_EN,
        'disclaimer_hi': DISCLAIMER_HI,
        'based_on': {'crop': crop or None, 'disease': disease or None,
                     'severity': severity or None, 'disease_confidence': confidence},
    }


def build_recommendations(report: dict) -> dict:
    """Deterministically generate safe guidance for ALL pipeline decisions.

    For an otherwise valid diseased result, recognized disease names receive
    low-risk, conditional care guidance even if disease confidence is low.
    Low confidence NEVER counts as a confirmed diagnosis or justifies treatment.
    For unusable images, crop disagreement, missing score or unknown diseases,
    use conservative general care instead.
    """
    report = report if isinstance(report, dict) else {}
    decision = _text(report.get('decision')).upper().replace(' ', '_')
    m1 = report.get('model1') or {}
    m2 = report.get('model2') or {}
    m3 = report.get('model3') or {}
    m0c = report.get('model0c') or {}
    if not isinstance(m1, dict): m1 = {}
    if not isinstance(m2, dict): m2 = {}
    if not isinstance(m3, dict): m3 = {}
    if not isinstance(m0c, dict): m0c = {}
    crop = _text(m0c.get('predicted_crop') or m2.get('crop'))
    disease = _text(m2.get('disease'))
    severity = _text(m3.get('severity'))
    confidence_raw = m2.get('confidence')
    confidence = float(confidence_raw) if isinstance(confidence_raw, (float, int)) and not isinstance(confidence_raw, bool) else None
    if confidence is not None and not (0 <= confidence <= 1): confidence = None
    args = {'crop': crop, 'disease': disease, 'severity': severity, 'confidence': confidence}

    if decision == 'HEALTHY' or m1.get('status') == 'HEALTHY' and decision == 'HEALTHY':
        return _payload('healthy', 'healthy_care', 'Keep your plant healthy', 'पौधे की सेहत बनाए रखें',
            ('Water according to the crop and soil condition; avoid overwatering.',
             'Maintain sufficient light and airflow around the plant.',
             'Inspect new leaves regularly for unusual spots or changes.'),
            ('फसल और मिट्टी की स्थिति के अनुसार पानी दें; ज्यादा पानी न दें।',
             'पौधे के आसपास पर्याप्त रोशनी और हवा बनाए रखें।',
             'नई पत्तियों में असामान्य धब्बे या बदलाव नियमित रूप से देखें।'), **args)

    if decision in {'RETAKE_IMAGE', 'NOT_USABLE_LEAF', 'CROP_NOT_VERIFIED'}:
        return _payload('retake', 'image_review', 'Take a clearer leaf photo', 'पत्ते की साफ़ फोटो लें',
            ('Photograph one leaf in even natural light.',
             'Keep the entire leaf visible and in focus.',
             'Select a supported crop and analyze again before following disease advice.'),
            ('एक पत्ते की समान प्राकृतिक रोशनी में फोटो लें।',
             'पूरा पत्ता साफ़ और फोकस में दिखाएँ।',
             'रोग की सलाह लेने से पहले समर्थित फसल की फिर जाँच करें।'), **args)

    agreement = report.get('crop_agreement')
    disagree = decision == 'REVIEW_CROP_DISAGREEMENT' or (isinstance(agreement, dict) and agreement.get('agree') is False)
    if disagree:
        return _payload('review', 'unverified_crop', 'Confirm the crop and disease first', 'पहले फसल और रोग की पुष्टि करें',
            ('Retake a clear photo of the same plant and analyze again.',
             'Monitor symptoms without assuming the suggested disease is confirmed.',
             'Ask a local agricultural expert to verify the crop and symptoms.'),
            ('उसी पौधे की साफ़ फोटो लेकर फिर विश्लेषण करें।',
             'अनुमानित रोग को पक्का माने बिना लक्षणों पर नज़र रखें।',
             'फसल और लक्षणों की पुष्टि स्थानीय कृषि विशेषज्ञ से कराएँ।'), **args)

    if decision != 'DISEASED_ANALYSIS_COMPLETE' or not disease or confidence is None:
        return _payload('general', 'low_confidence', 'Monitor the leaf and confirm symptoms', 'पत्ती पर नज़र रखें और लक्षण जाँचें',
            ('Take another clear photo and compare the result.',
             'Avoid wetting foliage unnecessarily; keep tools clean.',
             'Seek local agricultural advice before applying any treatment.'),
            ('एक और साफ़ फोटो लेकर परिणाम की तुलना करें।',
             'बिना जरूरत पत्तियों को गीला न करें और औज़ार साफ़ रखें।',
             'किसी भी उपचार से पहले स्थानीय कृषि विशेषज्ञ से सलाह लें।'), **args)

    match = next((rule for rule in RULES if any(term in disease.lower() for term in rule[1])), None)
    if match:
        rule_id, _, tips_en, tips_hi = match
    else:
        rule_id, tips_en, tips_hi = 'general_disease', BASE_TIPS_EN, BASE_TIPS_HI
    tips_en, tips_hi = list(tips_en), list(tips_hi)
    severity_key = severity.lower()
    if confidence < 0.50:
        # Never imply a low-scoring disease prediction is confirmed. Conditional,
        # non-chemical precautions still help users understand what to inspect.
        if match:
            title_en = f'Possible {disease.title()} — precautionary care'
            title_hi = f'संभावित {disease.title()} — सावधानी के उपाय'
            # A second look / expert verification is warranted, while preserving
            # the 3 condition-specific care tips from the matching rule.
            tips_en[2] += ' Confirm symptoms with a local expert before treatment.'
            tips_hi[2] += ' उपचार से पहले स्थानीय विशेषज्ञ से लक्षणों की पुष्टि कराएँ।'
            return _payload('disease_guidance', f'{rule_id}_unconfirmed', title_en, title_hi,
                            tuple(tips_en), tuple(tips_hi), **args)
        # Unknown name, so there is no grounded disease-specific matching rule.
        return _payload('general', 'unknown_disease_low_confidence',
                        'Uncertain disease — general care', 'रोग का अनुमान अनिश्चित — सामान्य देखभाल',
                        tuple(BASE_TIPS_EN), tuple(BASE_TIPS_HI), **args)

    if 'severe' in severity_key or 'high' in severity_key:
        tips_en[2] = 'Symptoms appear extensive; arrange prompt advice from a local agricultural expert.'
        tips_hi[2] = 'लक्षण ज्यादा दिख रहे हैं; जल्दी स्थानीय कृषि विशेषज्ञ की सलाह लें।'
    elif 'moderate' in severity_key:
        tips_en[2] = 'Recheck affected leaves over the next few days for signs of spreading.'
        tips_hi[2] = 'अगले कुछ दिनों में देखें कि प्रभावित भाग बढ़ तो नहीं रहे हैं।'
    title_en = f'Care suggestions for {disease.title()}' if match else 'Suggested plant care'
    title_hi = f'{disease.title()} के लिए देखभाल के सुझाव' if match else 'पौधे की देखभाल के सुझाव'
    return _payload('disease_guidance', rule_id, title_en, title_hi,
                    tuple(tips_en), tuple(tips_hi), **args)
