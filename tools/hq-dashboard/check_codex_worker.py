"""One fictional ChatGPT CLI connectivity check."""
import importlib.util
from pathlib import Path
import tempfile

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('hq_worker_smoke',HERE/'ai_tasks.py')
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
with tempfile.TemporaryDirectory(prefix='hq-cli-smoke-') as directory:
    prompt='''Connectivity check only. Do not call tools or read files. No career claims.
Return the required analysis JSON: is_job_posting false, readable true,
company and role empty, link and posting_text empty, score 1, verdict SKIP,
summary Fictional connectivity check, location_ok unclear, matches gaps flags empty arrays.'''
    result=worker.run_codex(prompt,'analyze',Path(directory),[])
    assert result.get('is_job_posting') is False and result.get('summary'), 'Unexpected smoke result'
    print('ChatGPT CLI worker connectivity: passed. No real posting, evidence or document was sent.')
