import unittest
from pathlib import Path
from unittest.mock import patch
from run_workflow import review, extract, MODELS


class WorkflowTests(unittest.TestCase):
    def test_detector_override_preserves_existing_default(self):
        with patch('run_workflow.subprocess.run') as run:
            extract(Path('image.jpg'), Path('out'), weights=Path('candidate.pt'))
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[cmd.index('--weights') + 1], 'candidate.pt')
            extract(Path('image.jpg'), Path('out'))
            cmd = run.call_args.args[0]
            self.assertTrue(cmd[cmd.index('--weights') + 1].endswith('detector.pt'))

    def test_both_optimized_profiles_use_automatic_topology(self):
        for profile in MODELS:
            with self.subTest(profile=profile), patch('run_workflow.subprocess.run') as run:
                review(Path('image.jpg'), Path('recognized.json'), Path('output'), profile)
                call = run.call_args
                command = call.args[0]
                self.assertIn('--netlist-image', command)
                self.assertEqual(command[command.index('--ocr-context') + 1], 'boxes')
                self.assertNotIn('--raw-netlist', command)
                self.assertEqual(call.kwargs['env']['ARK_MODEL'], MODELS[profile])
                self.assertTrue(call.kwargs['check'])


if __name__ == '__main__':
    unittest.main()
