"""Exercise updater in a synthetic repository and source contracts without live credentials."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess
import sys
import types
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
with TemporaryDirectory() as temp:
    root=Path(temp)/'repo'; target=root/'kekorea_risk_review_v2'; target.mkdir(parents=True)
    for path in HERE.glob('*.py'):
        if path.name!='self_test_patch.py':shutil.copy2(path,target/path.name)
    app=root/'Quotation_KEKOREA'; (app/'contracts').mkdir(parents=True)
    for file in (root/'README.md',app/'README.md',app/'README_CONTRACTS.md',app/'Team'/'README.md',app/'Presentation'/'README.md'):
        file.parent.mkdir(parents=True,exist_ok=True);file.write_text('existing README contents\n',encoding='utf-8')
    (app/'contracts'/'ui.py').write_text('''from Quotation_KEKOREA.contracts.workspace import collect_notes, propose_notes_revision

def _render_draft():
    if True:
        if True:
            if True:
                for sentence in []:
                    sentence_id = sentence['id']
                    if st.button(sentence['text'], key='thing'):
                        pass

def _note_row():
    pass

def render_contract_page():
    if True:
            # Contract RAG risk-review panel (read-only; user approval required)
            with st.expander('AI 핵심 위험 검토'):
                review_contract(snapshot, [] )
            with st.expander("Revision 기록 및 복원", expanded=False):
                pass
''',encoding='utf-8')
    first=subprocess.run([sys.executable,str(target/'apply_risk_review_v2.py')],cwd=root,capture_output=True,text=True)
    assert first.returncode == 0,(first.stdout,first.stderr)
    patched=(app/'contracts'/'ui.py').read_text()
    assert 'render_risk_review(repo, snapshot, state_key, env)' in patched
    assert 'st.button(displayed_text,' in patched
    assert (app/'contracts'/'risk_review_ui.py').exists()
    second=subprocess.run([sys.executable,str(target/'apply_risk_review_v2.py')],cwd=root,capture_output=True,text=True)
    assert second.returncode != 0,'Duplicate patch did not stop'
    print('PATCH: apply, backup and duplicate detection PASS')

# Minimal module stubs to test pure orchestration in this environment.
rootpkg=types.ModuleType('Quotation_KEKOREA');rootpkg.__path__=[]
contractpkg=types.ModuleType('Quotation_KEKOREA.contracts');contractpkg.__path__=[str(HERE)]
modedit=types.ModuleType('Quotation_KEKOREA.contracts.editing')
class RevisionConflict(ValueError):pass
modedit.RevisionConflict=RevisionConflict
modedit.find_sentence=lambda s,sid:next(x for c in s['clauses'] for x in c['sentences'] if x['id']==sid)
modedit.apply_proposal=lambda s,p,ids:s
modrev=types.ModuleType('Quotation_KEKOREA.contracts.review')
modrev.RISK_ORDER={'high':0,'medium':1,'low':2}
modrev.review_contract=lambda s,so,env:[]
modserv=types.ModuleType('Quotation_KEKOREA.contracts.service')
modserv._call=lambda *args,**kw:{}
modmodel=types.ModuleType('Quotation_KEKOREA.contracts.models')
modmodel.new_snapshot=lambda cid,t,l:{'contract_id':cid,'contract_type':t,'language':l,'clauses':[],'revision':1}
mods={'Quotation_KEKOREA':rootpkg,'Quotation_KEKOREA.contracts':contractpkg,
 'Quotation_KEKOREA.contracts.editing':modedit,'Quotation_KEKOREA.contracts.review':modrev,
 'Quotation_KEKOREA.contracts.service':modserv,'Quotation_KEKOREA.contracts.models':modmodel}
with patch.dict(sys.modules,mods):
    import importlib
    m=importlib.import_module('Quotation_KEKOREA.contracts.risk_review_workspace')
    tests=importlib.import_module('test_contract_risk_review_v2')
    import unittest
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestLoader().loadTestsFromModule(tests))
    assert result.wasSuccessful()
print('ORCHESTRATOR: pure regression tests PASS')
