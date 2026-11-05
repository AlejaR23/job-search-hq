"""Offline career task tests with fictional evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import uuid

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pc_ai_fixture',HERE/'ai_tasks.py')
ai=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)


class CareerTasks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='hq-ai-test-')
        self.state=Path(self.temp.name)
        self.calls=[]
        self.bank={'rules':'Fictional evidence only.','entries':{'E-999':{'level':'stated','text':'Fictional example skill.'}}}
        self.result={'is_job_posting':True,'readable':True,'company':'Example Company','role':'Example Role','link':'https://example.com',
                     'posting_text':'','score':3.5,'verdict':'CONSIDER','summary':'Fictional match.','location_ok':'unclear',
                     'matches':[{'requirement':'Example skill','evidence':'E-999','importance':'must','level':'partial'}],'gaps':[],'flags':[]}
        def fake(prompt,kind,folder,images):
            self.calls.append((prompt,kind,images))
            return self.result
        self.runner=fake
        self.tasks=ai.Tasks(self.state,runner=fake,bank_loader=lambda:self.bank)

    def tearDown(self):
        self.tasks.stop()
        self.temp.cleanup()

    def analyze(self):
        p={'kind':'analyze','requestId':str(uuid.uuid4()),'posting':{'company':'Example Company','role':'Example Role','link':'https://example.com','text':'Fictional posting requirements. '*10},'images':[]}
        key=self.tasks.submit(p)
        self.assertEqual(self.tasks.submit(p),key)
        self.tasks.process_one()
        self.assertEqual(self.tasks.list_tasks()[0]['status'],'done')
        return key

    def test_analyze_first_and_one_call(self):
        key=self.analyze()
        self.assertEqual(len(self.calls),1)
        self.assertFalse(self.tasks.posting(key)['reviewed'])
        self.assertNotIn('cv_markdown',self.tasks.posting(key)['fit'])
        self.assertIn('No tools, commands',self.calls[0][0])
        self.assertIn('E-999',self.calls[0][0])

    def test_letter_requires_explicit_sentiment_choice(self):
        key=self.analyze()
        with self.assertRaises(ValueError):
            self.tasks.submit({'kind':'letter','postingId':key,'requestId':str(uuid.uuid4())})
        self.result={'cover_letter_markdown':'Fictional letter.','sources':['E-999'],'flags':[],
                     'claims':[{'text':'Fictional letter.','evidence':['E-999']}]}
        self.tasks.submit({'kind':'letter','postingId':key,'sentiment':'Calm confidence','requestId':str(uuid.uuid4())})
        self.tasks.process_one()
        record=self.tasks.posting(key)
        self.assertEqual(record['fit']['sentiment'],'Calm confidence')
        self.assertFalse(record['reviewed'])
        self.assertEqual(self.tasks.list_tasks()[0]['status'],'done')

    def test_unknown_sources_are_blocked(self):
        key=self.analyze()
        self.result={'cv_markdown':'An invented claim.','sources':['E-013'],'flags':[],
                     'claims':[{'text':'An invented claim.','evidence':['E-013']}]}
        self.tasks.submit({'kind':'cv','postingId':key,'requestId':str(uuid.uuid4())})
        self.tasks.process_one()
        self.assertEqual(self.tasks.list_tasks()[0]['status'],'failed')
        self.assertNotIn('cv_markdown',self.tasks.posting(key)['fit'])

    def test_missing_analysis_and_invalid_photo(self):
        with self.assertRaises(ValueError):
            self.tasks.submit({'kind':'cv','postingId':str(uuid.uuid4()),'requestId':str(uuid.uuid4())})
        with self.assertRaises(ValueError):
            self.tasks.submit({'kind':'analyze','requestId':str(uuid.uuid4()),'posting':{'text':'Fake posting '*30},'images':['bm90LWFuLWltYWdl']})
        self.assertEqual(self.calls,[])

    def test_restart_does_not_duplicate_running_task(self):
        key=self.tasks.submit({'kind':'analyze','requestId':str(uuid.uuid4()),'posting':{'text':'Fictional posting '*20},'images':[]})
        with self.tasks.connect() as db,db:
            db.execute("UPDATE tasks SET status='running' WHERE id=?",(key,))
        resumed=ai.Tasks(self.state,runner=self.runner,bank_loader=lambda:self.bank)
        resumed.process_one()
        self.assertEqual(resumed.list_tasks()[0]['status'],'interrupted')
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main(verbosity=2)
