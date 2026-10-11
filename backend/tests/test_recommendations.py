"""Model-4 logic unit tests: run with `python -m unittest discover -s tests -p test_recommendations.py`."""
import unittest
from recommendations import build_recommendations


def report(decision='DISEASED_ANALYSIS_COMPLETE', disease='Tomato Late Blight',
           confidence=.86, severity='Mild', agree=True):
    return {'decision': decision,
            'model0c': {'predicted_crop': 'Tomato'},
            'model1': {'status': 'HEALTHY' if decision == 'HEALTHY' else 'DISEASED'},
            'model2': {'disease': disease, 'confidence': confidence},
            'model3': {'severity': severity},
            'crop_agreement': {'agree': agree}}


class RecommendationsTests(unittest.TestCase):
    def test_disease_specific_late_blight(self):
        item = build_recommendations(report())
        self.assertEqual(item['rule_id'], 'late_blight')
        self.assertEqual(item['status'], 'disease_guidance')
        self.assertEqual(len(item['tips_en']), 3)
        self.assertEqual(len(item['tips_hi']), 3)
        self.assertEqual(item['method'], 'rule_based')

    def test_severity_severe_escalates(self):
        item = build_recommendations(report(severity='Severe'))
        self.assertIn('prompt advice', item['tips_en'][2])

    def test_moderate_is_proportionate(self):
        item = build_recommendations(report(severity='Moderate'))
        self.assertIn('next few days', item['tips_en'][2])

    def test_healthy_avoids_disease_name(self):
        item = build_recommendations(report(decision='HEALTHY', disease='Late Blight'))
        self.assertEqual(item['status'], 'healthy')
        self.assertEqual(item['rule_id'], 'healthy_care')

    def test_low_confidence_gets_conditional_specific_care(self):
        item = build_recommendations(report(confidence=.201))
        self.assertEqual(item['rule_id'], 'late_blight_unconfirmed')
        self.assertEqual(item['version'], 2)
        self.assertEqual(item['status'], 'disease_guidance')
        self.assertIn('Possible', item['title_en'])
        self.assertIn('Late Blight', item['title_en'])
        self.assertIn('soil level', item['tips_en'][0])
        self.assertIn('before treatment', item['tips_en'][2])

    def test_low_confidence_unknown_disease_is_generic(self):
        item = build_recommendations(report(disease='Something Unclassified', confidence=.20))
        self.assertEqual(item['status'], 'general')
        self.assertEqual(item['rule_id'], 'unknown_disease_low_confidence')

    def test_missing_confidence_is_general(self):
        item = build_recommendations(report(confidence=None))
        self.assertEqual(item['status'], 'general')

    def test_disagree_requires_review(self):
        item = build_recommendations(report(decision='REVIEW_CROP_DISAGREEMENT', agree=False))
        self.assertEqual(item['status'], 'review')
        self.assertEqual(item['rule_id'], 'unverified_crop')

    def test_disagree_overrides_high_confidence(self):
        item = build_recommendations(report(agree=False))
        self.assertEqual(item['status'], 'review')

    def test_early_rejections(self):
        for decision in ('RETAKE_IMAGE', 'NOT_USABLE_LEAF', 'CROP_NOT_VERIFIED'):
            with self.subTest(decision=decision):
                self.assertEqual(build_recommendations({'decision': decision})['status'], 'retake')

    def test_general_unknown_disease(self):
        item = build_recommendations(report(disease='Some New Leaf Syndrome'))
        self.assertEqual(item['rule_id'], 'general_disease')

    def test_virus_rule(self):
        item = build_recommendations(report(disease='Tomato Yellow Leaf Curl Virus'))
        self.assertEqual(item['rule_id'], 'virus')

    def test_bacterial_rule(self):
        item = build_recommendations(report(disease='Bacterial spot'))
        self.assertEqual(item['rule_id'], 'bacterial')

    def test_powdery_rule(self):
        item = build_recommendations(report(disease='Powdery mildew'))
        self.assertEqual(item['rule_id'], 'powdery_mildew')

    def test_determinism_and_json_friendly(self):
        import json
        first = build_recommendations(report())
        self.assertEqual(first, build_recommendations(report()))
        self.assertIsInstance(json.dumps(first, ensure_ascii=False), str)

    def test_input_not_mutated(self):
        original = report()
        before = repr(original)
        build_recommendations(original)
        self.assertEqual(repr(original), before)


if __name__ == '__main__':
    unittest.main()
