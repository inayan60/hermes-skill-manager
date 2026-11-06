"""Profile isolation and native external_dirs selection (simulated Hermes scopes)."""
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MODULE = Path(__file__).resolve().parents[1] / 'dashboard' / 'plugin_api.py'
spec = importlib.util.spec_from_file_location('hsm_profile_test', MODULE)
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)
app = FastAPI()
app.include_router(api.router, prefix='/hsm')
client = TestClient(app)


def req(path, payload=None, *, good=True):
    response = client.get('/hsm'+path) if payload is None else client.post('/hsm'+path, json=payload)
    if good:
        assert response.status_code == 200, response.text
        return response.json()
    return response


@pytest.fixture
def hermes(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'appdata'))
    root = tmp_path / 'library'
    samples = ['jenkinsfile-generator', 'jenkinsfile-validator', 'bash-script-validator']
    for name in samples:
        p = root / 'skills' / 'owner' / 'repo' / 'nested' / name
        p.mkdir(parents=True)
        (p / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: Example for {name}\n---\n# Test\n')
    req('/settings', {'library_dir':str(root), 'hermes_dir':str(tmp_path/'hermes')})
    names = ['arthur-jenkins', 'jobson']
    configurations = {name: {'skills':{'external_dirs':[], 'disabled':[]}, 'model':{'provider':'unchanged'}} for name in names}
    configurations['jobson']['skills']['external_dirs'] = [str(tmp_path / 'other-source')]
    current = [None]
    def profiles():
        return [{'name':name,'display_name':name,'path':str(tmp_path/'hermes'/name)} for name in names]
    @contextmanager
    def fake_scope(name, *,write=False):
        current[0]=name
        def save():
            path = tmp_path / (name+'.json')
            path.write_text(json.dumps(configurations[name]))
        try:
            yield configurations[name], save
        finally:
            current[0]=None
    def fake_catalog():
        out=[]
        for mount in configurations[current[0]]['skills']['external_dirs']:
            folder=Path(mount)
            if not folder.is_dir():
                continue
            for md in folder.rglob('SKILL.md'):
                # mimic Hermes scanning only in the named profile
                out.append({'name':md.parent.name,'path':md,'status':'unique','load_name':md.parent.name})
        return out
    monkeypatch.setattr(api, '_native_profiles', profiles)
    monkeypatch.setattr(api, '_profile_config_scope', fake_scope)
    monkeypatch.setattr(api, '_native_resolved_catalog', fake_catalog)
    monkeypatch.setattr(api, '_disabled_config', lambda c: set(c.get('skills',{}).get('disabled',[])))
    return root, configurations, tmp_path


def test_profile_selection_does_not_copy_files(hermes):
    root, cfg, tmp = hermes
    available=req('/available-profiles')['profiles']
    assert {p['name'] for p in available} == {'arthur-jenkins','jobson'}
    state=req('/profile-skills?profile=arthur-jenkins')['skills']
    gen=next(x for x in state if x['name']=='jenkinsfile-generator')
    assert gen['status']=='pending_review'
    response=req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':gen['id'],'action':'enable'},good=False)
    assert response.status_code==409
    preview=req('/profile-skill-preview?skill_id='+gen['id'])
    assert 'name: jenkinsfile-generator' in preview['content']
    req('/reviews/set',{'skill_id':gen['id'],'approved':True})
    req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':gen['id'],'action':'enable'})
    arthur=req('/profile-skills?profile=arthur-jenkins')['skills']
    assert next(x for x in arthur if x['id']==gen['id'])['status']=='enabled'
    assert next(x for x in arthur if x['name']=='jenkinsfile-validator')['status']=='pending_review'
    assert len(cfg['arthur-jenkins']['skills']['external_dirs'])==1
    assert (root/'skills/owner/repo/nested/jenkinsfile-generator/SKILL.md').is_file()
    # Jobson config was not touched, even though both profiles use the same library.
    assert cfg['jobson']['skills']['external_dirs']==[str(tmp/'other-source')]
    assert cfg['jobson']['model']=={'provider':'unchanged'}
    assert not (tmp/'jobson.json').exists()
    assert (tmp/'arthur-jenkins.json').is_file()
    jobson=req('/profile-skills?profile=jobson')['skills']
    assert next(x for x in jobson if x['id']==gen['id'])['status']=='not_associated'

    req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':gen['id'],'action':'disable'})
    assert req('/profile-skills?profile=arthur-jenkins')['skills'][1]['status'] in ('disabled','pending_review')
    assert gen['name'] in cfg['arthur-jenkins']['skills']['disabled']
    req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':gen['id'],'action':'enable'})
    assert gen['name'] not in cfg['arthur-jenkins']['skills']['disabled']
    req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':gen['id'],'action':'detach'})
    assert cfg['arthur-jenkins']['skills']['external_dirs']==[]
    assert (root/'skills/owner/repo/nested/jenkinsfile-generator/SKILL.md').exists()


def test_ancestor_mount_is_not_modified(hermes):
    root, cfg, tmp=hermes
    parent=root/'skills'/'owner'/'repo'/'nested'
    cfg['arthur-jenkins']['skills']['external_dirs']=[str(parent)]
    rows=req('/profile-skills?profile=arthur-jenkins')['skills']
    assert all(x['association']=='inherited' for x in rows)
    first=rows[0]
    assert req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':first['id'],'action':'detach'},good=False).status_code==409
    req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':first['id'],'action':'disable'})
    assert cfg['arthur-jenkins']['skills']['external_dirs']==[str(parent)]
    assert cfg['arthur-jenkins']['skills']['disabled']==[first['name']]


def test_remove_blocks_in_use(hermes):
    root, cfg, tmp=hermes
    catalog=[{'id':'abc','name':'jenkinsfile-generator','relative_dir':'skills/owner/repo/nested/jenkinsfile-generator'}]
    api._catalog_write(root,catalog)
    cfg['arthur-jenkins']['skills']['external_dirs']=[str(root/'skills'/'owner'/'repo'/'nested'/'jenkinsfile-generator')]
    response=req('/remove',{'id':'abc'},good=False)
    assert response.status_code==409
    assert (root/'skills/owner/repo/nested/jenkinsfile-generator/SKILL.md').exists()


def test_approval_invalidated_by_content_change(hermes):
    root, cfg, tmp=hermes
    item=next(x for x in req('/profile-skills?profile=arthur-jenkins')['skills'] if x['name']=='jenkinsfile-generator')
    req('/reviews/set',{'skill_id':item['id'],'approved':True})
    after=next(x for x in req('/profile-skills?profile=arthur-jenkins')['skills'] if x['id']==item['id'])
    assert after['approved']
    (root / 'skills' / item['relative_dir'] / 'SKILL.md').write_text('---\nname: jenkinsfile-generator\n---\nmodified\n')
    altered=next(x for x in req('/profile-skills?profile=arthur-jenkins')['skills'] if x['id']==item['id'])
    assert not altered['approved']


def test_refuse_same_name_collision(hermes,monkeypatch):
    root,cfg,tmp=hermes
    item=next(x for x in req('/profile-skills?profile=arthur-jenkins')['skills'] if x['name']=='jenkinsfile-generator')
    req('/reviews/set',{'skill_id':item['id'],'approved':True})
    monkeypatch.setattr(api,'_native_resolved_catalog',lambda:[
        {'name':item['name'],'path':tmp/'local'/'jenkinsfile-generator'/'SKILL.md','status':'unique','load_name':item['name']}])
    assert req('/profile-skills/set',{'profile':'arthur-jenkins','skill_id':item['id'],'action':'enable'},good=False).status_code==409
    assert cfg['arthur-jenkins']['skills']['external_dirs']==[]


def test_approval_invalidated_when_aux_script_changes(hermes):
    root, cfg, tmp = hermes
    path=root/'skills/owner/repo/nested/jenkinsfile-generator'
    (path/'scripts').mkdir()
    (path/'scripts'/'run.sh').write_text('echo 1')
    item=next(x for x in req('/profile-skills?profile=arthur-jenkins')['skills'] if x['name']=='jenkinsfile-generator')
    req('/reviews/set', {'skill_id':item['id'],'approved':True})
    (path/'scripts'/'run.sh').write_text('echo 2')
    changed=next(x for x in req('/profile-skills?profile=arthur-jenkins')['skills'] if x['id']==item['id'])
    assert not changed['approved']


def test_catalogue_saved_at_parent_when_configured_skills_folder(hermes):
    root, cfg, tmp = hermes
    api._catalog_write(root,[{'id':'one','name':'jenkinsfile-generator',
                              'category':'CI/CD','relative_dir':'skills/owner/repo/nested/jenkinsfile-generator'}])
    req('/settings',{'library_dir':str(root/'skills'), 'hermes_dir':str(tmp/'hermes')})
    rows=req('/profile-skills?profile=arthur-jenkins')['skills']
    skill=next(x for x in rows if x['name']=='jenkinsfile-generator')
    assert skill['category']=='CI/CD'
    assert req('/state')['library'][0]['id']=='one'
    api._catalog_write(root/'skills',[{'id':'two','name':'other'}])
    assert json.loads((root/'catalogo.json').read_text())['skills'][0]['id']=='two'
    assert not (root/'skills'/'catalogo.json').exists()

def test_sync_removes_broad_mount_without_touching_other_profiles(hermes):
    root, cfg, tmp = hermes
    parent = root / 'skills' / 'owner' / 'repo'
    individual = root / 'skills' / 'owner' / 'repo' / 'nested' / 'jenkinsfile-generator'
    cfg['arthur-jenkins']['skills']['external_dirs'] = [str(parent), str(individual)]
    cfg['arthur-jenkins']['skills']['disabled'] = ['bash-script-validator']
    other = cfg['jobson']['skills']['external_dirs'][:]
    preview = req('/profile-skills/sync', {'profile':'arthur-jenkins','dry_run':True})
    assert preview['changed'] is True
    assert preview['remove'] == [str(parent)]
    assert cfg['arthur-jenkins']['skills']['external_dirs'] == [str(parent), str(individual)]
    applied = req('/profile-skills/sync', {'profile':'arthur-jenkins','dry_run':False})
    assert applied['changed'] is True
    assert cfg['arthur-jenkins']['skills']['external_dirs'] == [str(individual)]
    assert cfg['arthur-jenkins']['skills']['disabled'] == ['bash-script-validator']
    assert cfg['jobson']['skills']['external_dirs'] == other
    rows = req('/profile-skills?profile=arthur-jenkins')['skills']
    assert next(x for x in rows if x['name']=='jenkinsfile-generator')['association'] == 'individual'
    assert next(x for x in rows if x['name']=='jenkinsfile-validator')['association'] == 'none'
    assert req('/profile-skills/sync', {'profile':'arthur-jenkins','dry_run':False})['changed'] is False


def test_sync_does_not_mount_new_skills_or_change_unrelated_sources(hermes):
    root, cfg, tmp = hermes
    broad = root / 'skills'
    other = tmp / 'other'
    cfg['arthur-jenkins']['skills']['external_dirs'] = [str(other), str(broad)]
    req('/profile-skills/sync', {'profile':'arthur-jenkins','dry_run':False})
    assert cfg['arthur-jenkins']['skills']['external_dirs'] == [str(other)]
    new_skill = root / 'skills' / 'new-skill'
    new_skill.mkdir()
    (new_skill / 'SKILL.md').write_text('---\\nname: new-skill\\n---\\n# New\\n')
    items = req('/profile-skills?profile=arthur-jenkins')['skills']
    assert next(x for x in items if x['name']=='new-skill')['association'] == 'none'
