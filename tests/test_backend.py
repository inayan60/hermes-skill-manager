"""Offline smoke tests for the Hermes Skill Manager backend."""
import hashlib
import importlib.util
import sys
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'dashboard' / 'plugin_api.py'
spec = importlib.util.spec_from_file_location('skill_manager_api', MODULE)
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)
from fastapi import FastAPI
app = FastAPI()
app.include_router(api.router, prefix='/api/plugins/hermes-skill-manager')
client = TestClient(app)
URL = '/api/plugins/hermes-skill-manager'


def request(path, body=None):
    result = client.get(URL + path) if body is None else client.post(URL + path, json=body)
    assert result.status_code == 200, (path, result.status_code, result.text)
    return result.json()


@pytest.fixture(autouse=True)
def fake_network(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(api, '_native_profiles', lambda: [])
    commit = 'a' * 40
    blobs = {
        'skills/one/SKILL.md': b'---\nname: One Skill\ndescription: First test\ncategory: Infraestrutura\n---\n# One',
        'skills/one/scripts/run.sh': b'echo test\n',
        'skills/two/SKILL.md': b'---\nname: Two Skill\ndescription: Second test\n---\n# Two',
        'LICENSE': b'license',
        'plugin.yaml': b'name: other-plugin',
    }
    tree = [{'path':path,'type':'blob','mode':'100644','sha':api._git_hash(value),'size':len(value)}
            for path,value in blobs.items()]
    tree_sha='b'*40
    def fake_api(path):
        if path=='repos/example/repository':
            return {'default_branch':'main'}
        if path=='repos/example/repository/commits/main':
            return {'sha':commit,'commit':{'tree':{'sha':tree_sha}}}
        if path==f'repos/example/repository/git/trees/{tree_sha}?recursive=1':
            return {'tree':tree,'truncated':False}
        raise Exception('Unexpected API call: '+path)
    def fake_raw(repo, sha, path, limit):
        assert repo=='example/repository' and sha==commit
        assert len(blobs[path])<=limit
        return blobs[path]
    monkeypatch.setattr(api,'_api',fake_api)
    monkeypatch.setattr(api,'_raw',fake_raw)
    api._SCANS.clear()
    yield


def test_end_to_end(tmp_path):
    home=tmp_path/'library'
    result=request('/settings',{'library_dir':str(home),'hermes_dir':str(tmp_path/'hermes')})
    assert result['configured']
    scan=request('/discover',{'repository':'https://github.com/example/repository'})
    assert len(scan['skills'])==2
    assert 'One Skill' in [x['name'] for x in scan['skills']]
    one=next(x for x in scan['skills'] if x['name']=='One Skill')
    view=request('/preview',{'scan_id':scan['scan_id'],'path':one['path']})
    assert '# One' in view['content']
    out=request('/install',{'scan_id':scan['scan_id'],'items':[{'path':one['path'],'category':'Infraestrutura'}]})
    assert len(out['library'])==1
    item=out['library'][0]
    target=home/item['relative_dir']
    assert (target/'SKILL.md').exists()
    assert (target/'scripts'/'run.sh').read_bytes()==b'echo test\n'
    assert not (home/'plugin.yaml').exists()
    md=(home/'CATALOGO-SKILLS.md').read_text(encoding='utf-8')
    assert 'One Skill' in md
    assert len(json.loads((home/'catalogo.json').read_text())['skills'])==1
    request('/category',{'id':item['id'],'category':'DevOps'})
    assert request('/state')['library'][0]['category']=='DevOps'
    request('/update',{'id':item['id']})
    assert len(list((home/'.backups').iterdir()))==1
    assert request('/state')['library'][0]['category']=='DevOps'
    request('/remove',{'id':item['id']})
    assert not target.exists()
    assert len(list((home/'.lixeira').iterdir()))==1
    assert request('/state')['library']==[]


def test_bad_repo_and_unconfigured(tmp_path):
    assert client.post(URL+'/discover',json={'repository':'https://evil.example/repository'}).status_code==400
    assert client.post(URL+'/discover',json={'repository':'a/../../etc'}).status_code==400
    assert client.post(URL+'/install',json={'scan_id':'nope','items':[{'path':'a'}]}).status_code==400


def test_profiles_read_only(tmp_path):
    root=tmp_path/'hermes'
    (root/'skills'/'git').mkdir(parents=True)
    (root/'skills'/'git'/'SKILL.md').write_text('# test')
    request('/settings',{'library_dir':str(tmp_path/'library'),'hermes_dir':str(root)})
    listed=request('/profiles')
    assert listed['profiles'][0]['profile']=='default'
    assert listed['profiles'][0]['count']==1