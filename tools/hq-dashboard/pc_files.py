"""Allowlisted existing CV and draft exports."""
import hashlib
import os
import importlib.util
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
MIME='application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def existing(work=ROOT/'work'):
    out=[]
    for path in sorted(work.glob('CV_*.docx')):
        if path.is_symlink() or not path.resolve().is_relative_to(work.resolve()):continue
        if path.stat().st_size>5*1024*1024:continue
        key=hashlib.sha256(path.name.encode()).hexdigest()[:24]
        title=path.stem.removeprefix('CV_').replace('_',' ')
        out.append({'id':key,'name':path.name,'title':title,'company':title.split(' ')[0],
                    'reviewed':False,'updated':str(path.stat().st_mtime_ns),'bytes':path.stat().st_size,'mime':MIME})
    return out


def existing_file(key,work=ROOT/'work'):
    item=next((item for item in existing(work) if item['id']==key),None)
    if not item:raise ValueError('Unknown document.')
    return work/item['name']


def export_draft(state,posting_id,kind,record,copy_dir=None):
    if not re.fullmatch(r'[0-9a-f-]{36}',posting_id) or kind not in ('cv','letter'):
        raise ValueError('Invalid document request.')
    field='cv_markdown' if kind=='cv' else 'cover_letter_markdown'
    content=record.get('fit',{}).get(field)
    if not content:raise ValueError('Create this draft first.')
    spec=importlib.util.spec_from_file_location('hq_docx_converter',HERE/'docx_export.py')
    converter=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(converter)
    digest=hashlib.sha256(content.encode()).hexdigest()[:12]
    name=f'{kind.upper()}_DRAFT_{posting_id}_{digest}.docx'
    directory=state/'generated-documents'
    directory.mkdir(exist_ok=True)
    path=directory/name
    if not path.exists():
        temp=directory/(name+'.new.docx')
        converter.md_to_docx(content,temp)
        temp.replace(path)
    # Optional copy: set HQ_COPY_DIR to a synced folder. Content-addressed copies never overwrite an edited file.
    target=copy_dir if copy_dir is not None else (Path(os.environ['HQ_COPY_DIR']) if os.environ.get('HQ_COPY_DIR') else None)
    if target is not None and target.parent.is_dir():
        dest=target/'Drafts from HQ'
        dest.mkdir(parents=True,exist_ok=True)
        copy=dest/name
        if not copy.exists():copy.write_bytes(path.read_bytes())
    return path
