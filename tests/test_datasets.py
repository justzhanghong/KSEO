import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from importlib.resources import files

from kseo import datasets
from kseo.cli import main
from kseo.util import KSEOError


class DatasetTests(unittest.TestCase):
    def test_gsm8k_preserves_local_test_bytes_and_denominator(self):
        result = datasets.verify('gsm8k-main')
        counts = {f['filename']: f['records'] for f in result['files']}
        self.assertEqual(counts['test.jsonl'], 1319)
        self.assertNotIn('train.jsonl', counts)
        entry = datasets.load_dataset('gsm8k-main')
        self.assertEqual(entry['selection_authority'], 'local_frozen')
        test = next(f for f in entry['files'] if f['filename'] == 'test.jsonl')
        self.assertEqual(test['sha256'], '752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac')

    def test_local_longbench_retains_all_525_ids_and_105_contents(self):
        result = datasets.verify('longbench-v2')
        self.assertEqual(result['unique_ids'], 525)
        self.assertEqual(result['unique_contents'], 105)
        entry = datasets.load_dataset('longbench-v2')
        self.assertTrue(entry['final_accuracy_eligible'])
        self.assertEqual(entry['selection_authority'], 'local_frozen')
        self.assertEqual(entry['expected_samples'], 525)
        self.assertEqual(result['assembled_original_sha256'], 'b31bf65bdd0215568c888c192599b610b8316b2aadd3a0219d194c6480991b93')
        audit = json.loads(files('kseo').joinpath('data/datasets/longbench-historical-audit/audit.json').read_text())
        self.assertEqual(audit['unique_non_id_records'], 105)
        self.assertEqual(audit['multiplicity_histogram'], {'5': 105})

    def test_rtl_preserves_320_local_prompt_and_testbench_files(self):
        result = datasets.verify('rtlbench-160')
        self.assertEqual(result['unique_ids'], 160)
        base = files('kseo').joinpath('data/datasets/rtlbench')
        originals = {r['filename']: r['sha256'] for r in json.loads(base.joinpath('original-files.json').read_text())}
        self.assertEqual(len(originals), 320)
        for line in base.joinpath('test.jsonl').read_text().splitlines():
            row = json.loads(line)
            for suffix, value in [('desc.txt', row['prompt']), (row['testbench_filename'], row['testbench'])]:
                self.assertEqual(hashlib.sha256(value.encode()).hexdigest(), originals[row['sample_id'] + '/' + suffix])

    def test_export_is_checked_and_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'gsm8k'
            datasets.export('gsm8k-main', output)
            self.assertTrue(datasets.verify('gsm8k-main', output)['verified'])
            with self.assertRaises(KSEOError):
                datasets.export('gsm8k-main', output)
            p = output / 'test.jsonl'
            p.write_bytes(p.read_bytes() + b'\n')
            with self.assertRaises(KSEOError):
                datasets.verify('gsm8k-main', output)

    def test_private_data_stays_external_and_local_lcb_is_bundled_losslessly(self):
        for name in ('business-speed68', 'production-replay1200'):
            self.assertEqual(datasets.load_dataset(name)['distribution'], 'external')
            with self.assertRaises(KSEOError):
                datasets.verify(name)
        entry = datasets.load_dataset('livecodebench-v1')
        self.assertEqual(entry['distribution'], 'bundled')
        self.assertEqual(entry['selection_authority'], 'local_frozen')
        self.assertEqual(entry['expected_samples'], 400)
        self.assertEqual(len(set(entry['ordered_sample_ids'])), 400)
        self.assertEqual(entry['assembled_file']['sha256'], '2bd02b38beb48e8c46b5b9987095d999ff38cd8efc255ea5d58974317c48f63f')
        self.assertTrue(all(f['bytes'] < 100 * 1024 ** 2 for f in entry['files']))
        self.assertEqual(sum(f['format'] == 'gzip_part' for f in entry['files']), 24)
        self.assertFalse(any('url' in f for f in entry['files']))

    def test_failed_export_removes_only_its_fresh_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            keep = root / 'keep.txt'; keep.write_text('keep')
            with patch.object(datasets.shutil, 'copyfileobj', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    datasets.export('gsm8k-main', root / 'new')
            self.assertFalse((root / 'new').exists())
            self.assertEqual(keep.read_text(), 'keep')

    def test_cli_lists_verifies_and_rejects_ambiguous_operations(self):
        for argv, field in ((['dataset'], 'id'), (['dataset', 'gsm8k-main'], 'verified')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(argv), 0)
            value = json.loads(output.getvalue())
            self.assertIn(field, value[0] if isinstance(value, list) else value)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['dataset', '--out', 'unused']), 2)
            self.assertEqual(main(['dataset', 'gsm8k-main', '--root', '.', '--out', 'unused']), 2)
