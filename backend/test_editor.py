import tempfile
import unittest
from pathlib import Path
from fastapi import HTTPException
from freqtrade.rpc.api_server.api_local_strategies import Create, Save, create, get, save, target

class EditorChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = {'user_data_dir': Path(self.tmp.name), 'dry_run': True}
        (Path(self.tmp.name) / 'strategies').mkdir()
    def tearDown(self):
        self.tmp.cleanup()
    def test_create_copy_edit_backup_and_conflict(self):
        first = create(Create(name='Example'), self.config)
        clone = create(Create(name='ExampleCopy', source='Example'), self.config)
        self.assertIn('class ExampleCopy(', clone['content'])
        saved = save('ExampleCopy', Save(content=clone['content']+'\n# revised\n', revision=clone['revision']), self.config)
        self.assertNotEqual(saved['revision'], clone['revision'])
        self.assertEqual(len(list((Path(self.tmp.name)/'strategy_editor_backups/ExampleCopy').glob('*.py'))), 1)
        with self.assertRaises(HTTPException) as error:
            save('ExampleCopy', Save(content=clone['content'], revision=clone['revision']), self.config)
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(get('ExampleCopy',self.config)['revision'],saved['revision'])
    def test_invalid_input_does_not_overwrite(self):
        first=create(Create(name='Example'),self.config)
        for content in ['class Example(:', 'class Other: pass']:
            with self.assertRaises(HTTPException):
                save('Example',Save(content=content,revision=first['revision']),self.config)
        self.assertEqual(get('Example',self.config)['revision'],first['revision'])
        with self.assertRaises(HTTPException):create(Create(name='Example'),self.config)
    def test_restrict_paths_mode_and_active_paper(self):
        for name in ['../config','a/b','__init__','a.py','']:
            with self.assertRaises(HTTPException):target(name,self.config)
        with self.assertRaises(HTTPException):target('Example',{**self.config,'dry_run':False})
        x=create(Create(name='StarterFutures'),self.config)
        with self.assertRaises(HTTPException):save('StarterFutures',Save(content=x['content'],revision=x['revision']),self.config)
        p=Path(self.tmp.name)/'strategies/Link.py';p.symlink_to(Path(self.tmp.name)/'outside.py')
        with self.assertRaises(HTTPException):target('Link',self.config)

if __name__ == '__main__':unittest.main()
