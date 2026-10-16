import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import gui_workflow
from test_gui_contract import sample


class WorkflowIntegrationTests(unittest.TestCase):
    def run_case(self, cloud=False, error=None):
        with tempfile.TemporaryDirectory(prefix='sina-中文-') as directory:
            root = Path(directory)
            image = root / '电路.png'
            image.write_bytes(b'fixed image fixture')
            output = root / 'result'
            fake_torch = types.SimpleNamespace(set_num_threads=lambda n: None)
            with patch.dict(sys.modules, {'torch': fake_torch}), \
                 patch('gui_workflow.extract', return_value=sample()), \
                 patch('modules.vision.review_candidates', side_effect=error) as review:
                if isinstance(error, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        gui_workflow.recognize(image, output, root/'model', root, root, allow_cloud=cloud)
                else:
                    gui_workflow.recognize(image, output, root/'model', root, root, allow_cloud=cloud)
                called = review.call_count
            draft = json.loads((output/'recognized.json').read_text(encoding='utf-8'))
            events = [json.loads(line) for line in (output/'events.jsonl').read_text(encoding='utf-8').splitlines()]
            workflow = json.loads((output/'workflow.json').read_text(encoding='utf-8')) if (output/'workflow.json').exists() else None
            return draft, events, workflow, called, hashlib.sha256(image.read_bytes()).hexdigest()

    def test_offline_chinese_path_never_calls_cloud(self):
        draft, events, workflow, called, digest = self.run_case()
        self.assertEqual(called, 0)
        self.assertFalse(draft['ready_for_simulation'])
        self.assertFalse(draft['recognition']['user_confirmed'])
        self.assertEqual(draft['recognition']['image_sha256'], digest)
        self.assertEqual(events[-1]['status'], 'completed')

    def test_cloud_error_preserves_draft_without_secret(self):
        draft, events, workflow, called, digest = self.run_case(True, RuntimeError('secret-test-token'))
        self.assertEqual(workflow['cloud_error_type'], 'RuntimeError')
        self.assertFalse(workflow['cloud_completed'])
        self.assertNotIn('secret-test-token', json.dumps([draft, events, workflow]))
        self.assertFalse(draft['recognition']['user_confirmed'])

    def test_cancel_preserves_traceable_draft(self):
        draft, events, workflow, called, digest = self.run_case(True, KeyboardInterrupt())
        self.assertEqual(draft['recognition'].get('image_sha256'), digest)
        self.assertTrue(any(e['status'] == 'cancelled' for e in events))
        self.assertFalse(draft['ready_for_simulation'])

    def test_ocr_failure_is_measured_and_keeps_candidates(self):
        import argparse
        import local_extract
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image, weights = root/'input.png', root/'model.pt'
            image.write_bytes(b'fixture')
            weights.write_bytes(b'fixture weights')
            args = argparse.Namespace(image=image, weights=weights, out=root/'out',
                device='0', conf=.25, imgsz=960, detections=None, skip_ocr=False,
                skip_crossings=True, ocr_model_dir=root, ocr_user_dir=root/'ocr', ocr_optional=True)
            with patch.dict(sys.modules, {'cv2': types.SimpleNamespace(), 'numpy': types.SimpleNamespace()}), \
                 patch('local_extract.read_image', return_value=object()), \
                 patch('local_extract.detector.detect', return_value=([], {})), \
                 patch('local_extract.topology.analyze', return_value=([], None)), \
                 patch('local_extract.attach_pins', return_value={}), \
                 patch('local_extract.ocr_stage.recognize', side_effect=RuntimeError('secret-token')):
                result = local_extract.extract(args)
            self.assertEqual(result['stage_metrics']['ocr']['status'], 'failed')
            self.assertEqual(result['stage_metrics']['ocr']['error_type'], 'RuntimeError')
            self.assertNotIn('secret-token', json.dumps(result))
            self.assertEqual(result['ocr'], [])
            self.assertTrue(result['warnings'])
            for name in ('detection', 'topology', 'pins'):
                self.assertEqual(result['stage_metrics'][name]['status'], 'completed')
                self.assertGreaterEqual(result['stage_metrics'][name]['seconds'], 0)

    def test_previous_failed_attempt_logs_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'output'
            output.mkdir()
            (output/'events.jsonl').write_text('previous failure', encoding='utf-8')
            fake_torch = types.SimpleNamespace(set_num_threads=lambda n: None)
            with patch.dict(sys.modules, {'torch': fake_torch}), patch('gui_workflow.extract') as extract:
                with self.assertRaises(ValueError):
                    gui_workflow.recognize('missing.png', output, 'model.pt', '.', '.')
            extract.assert_not_called()
            self.assertEqual((output/'events.jsonl').read_text(), 'previous failure')

    def test_local_failure_has_failed_event_and_no_fake_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'output'
            fake_torch = types.SimpleNamespace(set_num_threads=lambda n: None)
            with patch.dict(sys.modules, {'torch': fake_torch}), patch('gui_workflow.extract', side_effect=ValueError('secret-input')):
                with self.assertRaises(ValueError):
                    gui_workflow.recognize('missing.png', output, 'model.pt', '.', '.')
            self.assertFalse((output/'recognized.json').exists())
            event = json.loads((output/'events.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(event['status'], 'failed')
            self.assertNotIn('secret-input', json.dumps(event))

    def test_explicit_weights_does_not_require_default_model(self):
        with patch.object(sys, 'argv', ['gui_workflow.py', 'image.png', '--out', 'out', '--weights', 'custom.pt']), patch('gui_workflow.selected_weights', side_effect=ValueError('default model unavailable')) as selected, patch('gui_workflow.recognize') as recognize:
            gui_workflow.main()
        selected.assert_not_called()
        self.assertEqual(recognize.call_args.args[2], Path('custom.pt'))

    def test_cli_exposes_inference_parameters(self):
        with patch.object(sys, 'argv', ['gui_workflow.py', 'image.png', '--out', 'out', '--device', '0', '--imgsz', '640', '--conf', '0.3']), patch('gui_workflow.selected_weights', return_value=Path('model.pt')), patch('gui_workflow.recognize') as recognize:
            gui_workflow.main()
        self.assertEqual(recognize.call_args.kwargs['device'], '0')
        self.assertEqual(recognize.call_args.kwargs['imgsz'], 640)
        self.assertEqual(recognize.call_args.kwargs['conf'], 0.3)


if __name__ == '__main__':
    unittest.main()
