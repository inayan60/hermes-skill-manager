"""Hermes Skill Manager REST API. Requires the Agent plugin to be enabled.

Only public github.com repositories are supported. Files are copied into the
configured library; this module never executes them or touches bot profiles.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
_LOCK = threading.RLock()
_SCANS = {}
_MAX_SCANS = 12
_MAX_SKILLS = 1500
_MAX_FILES = 400
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_SKILL_BYTES = 60 * 1024 * 1024
_MAX_SKILL_MD = 512 * 1024
_ALLOWED_ROOT_ASSETS = {'SKILL.md', 'README.md', 'LICENSE', 'LICENSE.md'}
_ALLOWED_ROOT_DIRS = {'references', 'scripts', 'assets', 'templates', 'examples'}
REPO_RE = re.compile(r'^[A-Za-z\d_.-]+/[A-Za-z\d_.-]+$')
SHA_RE = re.compile(r'^[0-9a-f]{40}$')


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _preferences_file():
    base = Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.config'))
    return base / 'HermesSkillManagerPlugin' / 'settings.json'


def _default_hermes():
    return str(Path(os.environ.get('HERMES_HOME') or
                    (Path(os.environ['LOCALAPPDATA']) / 'hermes' if os.environ.get('LOCALAPPDATA')
                     else Path.home() / '.hermes')))


def _settings():
    defaults = {'library_dir': '', 'hermes_dir': _default_hermes()}
    try:
        obj = json.loads(_preferences_file().read_text(encoding='utf-8'))
        if isinstance(obj, dict):
            return {k: obj.get(k, v) if isinstance(obj.get(k, v), str) else v for k, v in defaults.items()}
    except (FileNotFoundError, OSError, ValueError):
        pass
    return defaults


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic file replacement; no temporary files left behind on failure.
    fd, filename = tempfile.mkstemp(prefix='.hsm-', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def _library(create=False):
    value = _settings().get('library_dir', '').strip()
    if not value:
        raise HTTPException(400, 'Configure a pasta da biblioteca em Configurações antes de instalar.')
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    if not path.is_absolute():
        raise HTTPException(400, 'A pasta da biblioteca precisa ser um caminho absoluto.')
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(400, f'Não foi possível acessar a biblioteca: {exc}') from exc
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, 'Pasta da biblioteca não encontrada.')
    return path.resolve()


def _secure_relative(path: str):
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('Caminho inválido no repositório.')
    p = PurePosixPath(path)
    if p.is_absolute() or any(x in ('..', '.', '') for x in p.parts) or ':' in path:
        raise ValueError('Caminho inválido no repositório.')
    return p


def _child(root: Path, *pieces: str):
    rel = PurePosixPath('/'.join(pieces))
    _secure_relative(str(rel))
    target = root.joinpath(*rel.parts)
    # Reject pre-existing symlink escapes (e.g. a malicious library path).
    if not target.resolve().is_relative_to(root.resolve()):
        raise HTTPException(400, 'Caminho fora da biblioteca.')
    return target


def _repository(spec: str):
    spec = spec.strip().rstrip('/')
    if spec.startswith(('https://', 'http://')):
        parsed = urlsplit(spec)
        if parsed.scheme != 'https' or parsed.hostname not in ('github.com', 'www.github.com') or parsed.port:
            raise HTTPException(400, 'Use um repositório público em https://github.com.')
        spec = parsed.path.strip('/')
    if spec.endswith('.git'):
        spec = spec[:-4]
    if not REPO_RE.fullmatch(spec) or any(x in ('.', '..') for x in spec.split('/')):
        raise HTTPException(400, 'Informe dono/repositório ou https://github.com/dono/repositório.')
    return spec


def _fetch(url, limit=10 * 1024 * 1024):
    req = Request(url, headers={'User-Agent': 'HermesSkillManager/1.1', 'Accept': 'application/vnd.github+json'})
    try:
        with urlopen(req, timeout=25) as resp:
            size = resp.headers.get('Content-Length')
            if size is not None and int(size) > limit:
                raise HTTPException(413, 'Arquivo excede o limite de tamanho.')
            data = resp.read(limit + 1)
            if len(data) > limit:
                raise HTTPException(413, 'Arquivo excede o limite de tamanho.')
            return data
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise HTTPException(429, 'Limite de acesso ao GitHub ou acesso negado. Aguarde e tente novamente.') from exc
        if exc.code == 404:
            raise HTTPException(404, 'Repositório ou arquivo não encontrado no GitHub.') from exc
        raise HTTPException(502, f'Falha de comunicação com GitHub (HTTP {exc.code}).') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise HTTPException(502, f'Não foi possível acessar o GitHub: {exc}') from exc


def _api(path: str):
    return json.loads(_fetch('https://api.github.com/' + path, limit=8 * 1024 * 1024))


def _raw(repo, commit, path, limit):
    safe = '/'.join(quote(p, safe='') for p in _secure_relative(path).parts)
    return _fetch(f'https://raw.githubusercontent.com/{repo}/{commit}/{safe}', limit=limit)


def _git_hash(data: bytes):
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\x00' + data).hexdigest()


def _verified_blob(repo, commit, entry, limit):
    data = _raw(repo, commit, entry['path'], limit)
    if _git_hash(data) != entry['sha']:
        raise HTTPException(409, f'GitHub retornou conteúdo diferente da revisão fixada: {entry["path"]}')
    return data


def _skill_info(body: str, fallback: str):
    front = body.split('---', 2)
    source = front[1] if body.lstrip().startswith('---') and len(front) > 2 else ''
    out = {}
    for key in ('name', 'description', 'version', 'category'):
        m = re.search(rf'^\s*{key}\s*:\s*(.+?)\s*$', source, flags=re.I | re.M)
        if m:
            out[key] = m.group(1).strip().strip('\"\'')
    out.setdefault('name', fallback)
    out.setdefault('description', '')
    out.setdefault('version', '')
    out.setdefault('category', _category(out['name'] + ' ' + out['description']))
    return out


def _category(txt: str):
    t = txt.lower()
    for name, terms in (
        ('Desenvolvimento', ('code', 'coding', 'python', 'typescript', 'git ', 'programming')),
        ('Infraestrutura', ('devops', 'docker', 'kubernetes', 'server', 'cloud', 'linux', 'network')),
        ('Segurança', ('security', 'audit', 'pentest', 'vulnerability', 'secure')),
        ('Pesquisa', ('research', 'search', 'study', 'web browse')),
        ('Documentação', ('document', 'markdown', 'pdf', 'office')),
        ('Automação', ('automation', 'workflow', 'agent', 'orchestration')),
    ):
        if any(term in t for term in terms):
            return name
    return 'Geral'


def _entry_key(repo, folder):
    return hashlib.sha256((repo + '/' + folder).encode()).hexdigest()[:20]


def _scan_repo(repo: str, read_previews=True):
    parts = repo.split('/')
    meta = _api('repos/' + '/'.join(quote(x, safe='') for x in parts))
    branch = meta.get('default_branch')
    if not branch:
        raise HTTPException(422, 'Repositório sem branch padrão.')
    last = _api('repos/' + repo + '/commits/' + quote(branch, safe=''))
    commit = last.get('sha', '')
    tree_sha = last.get('commit', {}).get('tree', {}).get('sha', '')
    if not SHA_RE.fullmatch(commit) or not SHA_RE.fullmatch(tree_sha):
        raise HTTPException(502, 'GitHub não retornou um commit válido.')
    tree = _api('repos/' + repo + '/git/trees/' + tree_sha + '?recursive=1')
    if tree.get('truncated'):
        raise HTTPException(422, 'A árvore do repositório é muito grande e foi truncada pelo GitHub.')
    blobs = {}
    for e in tree.get('tree', []):
        path = e.get('path', '')
        if e.get('type') != 'blob' or e.get('mode') == '120000':
            continue
        try:
            _secure_relative(path)
        except ValueError:
            continue
        if not SHA_RE.fullmatch(e.get('sha', '')):
            continue
        blobs[path] = {'path': path, 'sha': e['sha'], 'size': e.get('size', 0)}
    skill_paths = sorted(p for p in blobs if p.lower() == 'skill.md' or p.lower().endswith('/skill.md'))
    if len(skill_paths) > _MAX_SKILLS:
        raise HTTPException(413, f'Repositório com mais de {_MAX_SKILLS} skills; limite excedido.')
    skills = []
    by_path = {}
    for i, path in enumerate(skill_paths):
        folder = path[:-len('/SKILL.md')] if '/' in path else '.'
        if folder != '.':
            # Files below an independently installable nested skill are not included.
            member = [x for x in blobs if x.startswith(folder + '/') and not any(
                x.startswith(child[:-len('/SKILL.md')] + '/') for child in skill_paths
                if child != path and '/' in child and child.startswith(folder + '/')
            )]
        else:
            member = [x for x in blobs if x in _ALLOWED_ROOT_ASSETS or
                      x.split('/')[0] in _ALLOWED_ROOT_DIRS]
        title = folder.split('/')[-1] if folder != '.' else repo.split('/')[1]
        item = {'path': folder, 'name': title, 'description': '', 'category': _category(title),
                'version': '', 'file_count': len(member), 'preview': '', 'preview_loaded': False,
                'installed_key': _entry_key(repo, folder)}
        if read_previews and i < 35:
            blob = _verified_blob(repo, commit, blobs[path], _MAX_SKILL_MD)
            info = _skill_info(blob.decode('utf-8', 'replace'), title)
            item.update(info)
            item['preview'] = blob.decode('utf-8', 'replace')[:10000]
            item['preview_loaded'] = True
        skills.append(item)
        by_path[folder] = {'header': blobs[path], 'members': [blobs[x] for x in sorted(member)], 'item': item}
    token = secrets.token_urlsafe(21)
    with _LOCK:
        while len(_SCANS) >= _MAX_SCANS:
            _SCANS.pop(next(iter(_SCANS)))
        _SCANS[token] = {'repo': repo, 'commit': commit, 'skills': by_path}
    return {'scan_id': token, 'repository': repo, 'commit': commit, 'skills': skills,
            'note': 'Prévia automática limitada às primeiras 35 skills. Use Prévia nas demais.' if len(skills) > 35 else ''}


def _scan(scan_id):
    with _LOCK:
        scan = _SCANS.get(scan_id)
    if not scan:
        raise HTTPException(400, 'Pesquisa expirada. Analise o repositório novamente.')
    return scan


def _catalog(root):
    try:
        data = json.loads((root / 'catalogo.json').read_text(encoding='utf-8'))
        if isinstance(data, dict) and isinstance(data.get('skills'), list):
            return data['skills']
    except (FileNotFoundError, OSError, ValueError):
        pass
    return []


def _catalog_write(root, items):
    _save_json(root / 'catalogo.json', {'schema': 1, 'updated_at': _now(), 'skills': items})
    md = ['# Catálogo de skills aprovadas / em curadoria', '',
          '> Biblioteca de arquivos; não significa que as skills estejam habilitadas nos perfis Hermes.', '',
          '| Skill | Categoria | Origem | Commit | Pasta |', '|---|---|---|---|---|']
    for item in sorted(items, key=lambda i: (i.get('category', ''), i.get('name', ''))):
        safe = lambda v: str(v or '').replace('|', '\\|').replace('\n', ' ')
        md.append(f"| {safe(item.get('name'))} | {safe(item.get('category'))} | "
                  f"{safe(item.get('repository'))} | {safe(item.get('commit', '')[:10])} | "
                  f"{safe(item.get('relative_dir'))} |")
    md += ['', '## Notas', '', 'As skills são textos e arquivos de terceiros. Revise-as antes de habilitar em um bot.',
           'Nenhuma alteração de perfil é feita por este gerenciador.', '']
    target = root / 'CATALOGO-SKILLS.md'
    temp = root / '.CATALOGO-SKILLS.md.tmp'
    temp.write_text('\n'.join(md), encoding='utf-8')
    os.replace(temp, target)


def _install_one(scan, path, category, root, entries):
    found = scan['skills'].get(path)
    if not found:
        raise HTTPException(400, f'Skill não encontrada na pesquisa: {path}')
    members = found['members']
    if len(members) > _MAX_FILES:
        raise HTTPException(413, f'Skill excede {_MAX_FILES} arquivos.')
    sum_size = sum(max(0, int(x.get('size') or 0)) for x in members)
    if sum_size > _MAX_SKILL_BYTES:
        raise HTTPException(413, 'Skill excede 60 MB.')
    repo = scan['repo']
    owner, repo_name = repo.split('/')
    base = f'skills/{owner}/{repo_name}'
    rel = f'{base}/{path}' if path != '.' else f'{base}/_root'
    target = _child(root, rel)
    stage = _child(root, f'.stage/{secrets.token_hex(12)}')
    stage.mkdir(parents=True, exist_ok=False)
    saved = False
    try:
        for entry in members:
            full = entry['path']
            suffix = full[len(path) + 1:] if path != '.' else full
            _secure_relative(suffix)
            size = int(entry.get('size') or 0)
            if size > _MAX_FILE_BYTES:
                raise HTTPException(413, f'Arquivo acima de 8 MB: {full}')
            data = _verified_blob(repo, scan['commit'], entry, _MAX_FILE_BYTES)
            dest = _child(stage, suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        if not (stage / 'SKILL.md').is_file():
            raise HTTPException(422, 'Skill sem SKILL.md na pasta selecionada.')
        if target.exists():
            backup = _child(root, f'.backups/{_entry_key(repo, path)}-{secrets.token_hex(6)}')
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(backup))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage), str(target))
        saved = True
        meta = found['item']
        entry = {'id': _entry_key(repo, path), 'name': meta['name'],
                 'description': meta.get('description', ''), 'category': category or meta['category'],
                 'version': meta.get('version', ''), 'repository': repo,
                 'repo_path': path, 'relative_dir': rel, 'commit': scan['commit'],
                 'file_count': len(members), 'installed_at': _now()}
        entries[:] = [i for i in entries if i.get('id') != entry['id']]
        entries.append(entry)
        return entry
    finally:
        if not saved and stage.exists():
            shutil.rmtree(stage)


class SettingsInput(BaseModel):
    library_dir: str = Field(max_length=1200)
    hermes_dir: str = Field(max_length=1200)


class RepoInput(BaseModel):
    repository: str = Field(min_length=1, max_length=250)


class PreviewInput(BaseModel):
    scan_id: str
    path: str


class Selection(BaseModel):
    path: str
    category: str = Field(default='', max_length=80)


class InstallInput(BaseModel):
    scan_id: str
    items: list[Selection] = Field(min_length=1, max_length=50)


class IdInput(BaseModel):
    id: str


class CategoryInput(IdInput):
    category: str = Field(min_length=1, max_length=80)


@router.get('/state')
def state():
    settings = _settings()
    root = Path(settings['library_dir']) if settings['library_dir'] else None
    items = _catalog(root) if root and root.is_dir() else []
    return {'settings': settings, 'library': items, 'configured': bool(root and root.is_dir())}


@router.post('/settings')
def settings_update(body: SettingsInput):
    library = Path(os.path.expandvars(os.path.expanduser(body.library_dir.strip())))
    hermes = Path(os.path.expandvars(os.path.expanduser(body.hermes_dir.strip())))
    if not body.library_dir.strip() or not library.is_absolute() or not hermes.is_absolute():
        raise HTTPException(400, 'Informe caminhos absolutos para biblioteca e Hermes.')
    try:
        library.mkdir(parents=True, exist_ok=True)
        probe = library / ('.hsm-probe-' + secrets.token_hex(6))
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
    except OSError as exc:
        raise HTTPException(400, f'Biblioteca sem permissão de gravação: {exc}') from exc
    with _LOCK:
        _save_json(_preferences_file(), {'library_dir': str(library), 'hermes_dir': str(hermes)})
    return state()


@router.post('/discover')
def discover(body: RepoInput):
    return _scan_repo(_repository(body.repository))


@router.post('/preview')
def preview(body: PreviewInput):
    scan = _scan(body.scan_id)
    found = scan['skills'].get(body.path)
    if found is None:
        raise HTTPException(404, 'Skill não encontrada nesta pesquisa.')
    info = found['item']
    if not info['preview_loaded']:
        blob = _verified_blob(scan['repo'], scan['commit'], found['header'], _MAX_SKILL_MD)
        content = blob.decode('utf-8', 'replace')
        info.update(_skill_info(content, info['name']))
        info['preview'] = content[:20000]
        info['preview_loaded'] = True
    return {'item': info, 'content': info['preview']}


@router.post('/install')
def install(body: InstallInput):
    scan = _scan(body.scan_id)
    root = _library(create=True)
    with _LOCK:
        entries = _catalog(root)
        changed = []
        for item in body.items:
            changed.append(_install_one(scan, item.path, item.category.strip(), root, entries))
            _catalog_write(root, entries)
    return {'installed': changed, 'library': entries}


@router.post('/update')
def update(body: IdInput):
    root = _library()
    with _LOCK:
        entries = _catalog(root)
        existing = next((x for x in entries if x.get('id') == body.id), None)
        if not existing:
            raise HTTPException(404, 'Skill não encontrada na biblioteca.')
        scan_result = _scan_repo(existing['repository'], read_previews=False)
        scan = _scan(scan_result['scan_id'])
        if existing['repo_path'] not in scan['skills']:
            raise HTTPException(404, 'Essa skill não existe mais no repositório.')
        item = _install_one(scan, existing['repo_path'], existing.get('category', 'Geral'), root, entries)
        _catalog_write(root, entries)
    return {'updated': item, 'library': entries}


@router.post('/category')
def category_update(body: CategoryInput):
    root = _library()
    with _LOCK:
        entries = _catalog(root)
        item = next((x for x in entries if x.get('id') == body.id), None)
        if not item:
            raise HTTPException(404, 'Skill não encontrada.')
        item['category'] = body.category.strip()
        _catalog_write(root, entries)
    return {'library': entries}


@router.post('/remove')
def remove(body: IdInput):
    root = _library()
    with _LOCK:
        entries = _catalog(root)
        item = next((x for x in entries if x.get('id') == body.id), None)
        if not item:
            raise HTTPException(404, 'Skill não encontrada.')
        target = _child(root, item['relative_dir'])
        if target.exists():
            trash = _child(root, f'.lixeira/{item["id"]}-{secrets.token_hex(6)}')
            trash.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(trash))
        entries = [x for x in entries if x.get('id') != body.id]
        _catalog_write(root, entries)
    return {'library': entries}


@router.get('/profiles')
def profiles():
    root = Path(_settings()['hermes_dir'])
    bases = []
    if (root / 'skills').is_dir():
        bases.append(('default', root / 'skills'))
    parent = root / 'profiles'
    if parent.is_dir():
        for p in parent.iterdir():
            if p.is_dir() and (p / 'skills').is_dir():
                bases.append((p.name, p / 'skills'))
    result = []
    for name, skills_dir in bases:
        count = 0
        sample = []
        for here, subdirs, files in os.walk(skills_dir, followlinks=False):
            subdirs[:] = [x for x in subdirs if not (Path(here) / x).is_symlink()]
            if 'SKILL.md' in files:
                count += 1
                if len(sample) < 100:
                    sample.append(str(Path(here).relative_to(skills_dir)))
            if count >= 3000:
                break
        result.append({'profile': name, 'count': count, 'sample': sample})
    return {'profiles': result, 'hermes_dir': str(root),
            'note': 'Busca local somente leitura nas pastas de skills encontradas. Perfis com outro layout podem não aparecer.'}