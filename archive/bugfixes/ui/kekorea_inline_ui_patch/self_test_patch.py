"""Offline smoke test of the patch transform and backup/dedupe checks."""
import importlib.util
import tempfile
from pathlib import Path

spec=importlib.util.spec_from_file_location('patcher',Path(__file__).with_name('apply_inline_ui_patch.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    ui=root/'Quotation_KEKOREA/contracts/ui.py'
    ui.parent.mkdir(parents=True)
    # Emulate the exact relevant source layout of the latest remote ui.py.
    source='''def f(st, sentence, contract_id, opened, revision, snapshot, annotations, saved_notes, buffers, repo, state_key, env, pending, buffer_key):
    st.markdown("""<style>
'''+module.CSS_OLD+'''    </style>""", unsafe_allow_html=True)
    if True:
        if True:
            if True:
                for sentence in [sentence]:
                    sentence_id = sentence['id']
                    is_open = sentence_id in opened
'''+module.BEFORE+'''
                        note = st.text_area("메모", key=sentence_id)
                        with st.expander("고급"):
                            st.button("메모 저장")
    _batch_request_panel(repo, snapshot, state_key, env, pending, buffers)
'''
    ui.write_text(source,encoding='utf-8')
    for p in module.READMES:
        local=root/p.relative_to(module.ROOT)
        local.parent.mkdir(parents=True,exist_ok=True)
        local.write_text('# Mock README\n',encoding='utf-8')
    module.ROOT=root
    module.UI=ui
    module.READMES=[root/'README.md',root/'Quotation_KEKOREA/README.md',root/'Quotation_KEKOREA/README_CONTRACTS.md',root/'Quotation_KEKOREA/Team/README.md',root/'Quotation_KEKOREA/Presentation/README.md']
    module.run()
    changed=ui.read_text(encoding='utf-8')
    assert 'text_col, note_col = st.columns([7, 3], gap="medium", vertical_alignment="top")' in changed
    assert 'with st.container(border=True):' in changed
    assert changed.index('with st.container(border=True)') < changed.index('note = st.text_area')
    assert '    _batch_request_panel(repo, snapshot, state_key, env, pending, buffers)' in changed
    assert len(list(root.glob('.local_contract_ui_backup_*')))==1
    for p in module.READMES:
        assert len(p.read_text(encoding='utf-8'))>100
    try:
        module.run()
        raise AssertionError('Second run did not stop')
    except SystemExit as exc:
        assert 'already applied' in str(exc)
print('PASS: transform, Python syntax, backups, README updates, double-apply guard')
