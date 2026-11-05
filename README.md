# Hermes Skill Manager v1.2.1

Plugin **unificado** (Agent + Desktop) para Hermes Agent v0.22.7+. Gerencia uma biblioteca compartilhada de skills com seleção individual do GitHub, organização por categoria e catálogo para seus bots. **Não adiciona ferramentas ao modelo, não ativa skills em perfis e não faz chamadas de IA.**

## Instalação pelo Hermes — comando único

Depois que **este conteúdo estiver publicado na raiz** de `https://github.com/inayan60/hermes-skill-manager`:

```powershell
hermes -p infra plugins install inayan60/hermes-skill-manager --enable
```

> **Importante:** `-p infra` significa *perfil chamado `infra`*. A sintaxe `hermes -infra ...` não é reconhecida pelo CLI oficial. Se não existir um perfil `infra`, use `hermes plugins install inayan60/hermes-skill-manager --enable` para o perfil ativo, ou substitua `infra` pelo perfil correto. Liste os perfis com `hermes profile list`.

O Hermes faz o clone, verifica o plugin, instala em `plugins/hermes-skill-manager/` no perfil selecionado e ativa **a parte Python (Agent)** por causa de `--enable`. Nenhum `.exe`, comando de cópia, script de dependências nem instalação manual de arquivos é necessário.

O **Desktop** reconhece a pasta `desktop/plugin.js` do mesmo pacote e a materializa automaticamente na biblioteca de extensões do aplicativo. Há uma diferença **do próprio Hermes**: a parte Desktop tem uma opção de habilitação separada e *opt-in*. Com `--enable` no terminal, **não é possível garantir** que a interface será ativada automaticamente, especialmente na primeira instalação. Se a opção **Skill Manager** não surgir, abra **Capabilities → Plugins**, encontre **Hermes Skill Manager** e habilite a parte **Desktop**. Esse consentimento não pode ser contornado por um plugin ainda desabilitado. Quando o Hermes Desktop instala o pacote pela sua própria interface, consegue habilitar as duas partes durante a instalação.

O serviço do backend também pode precisar ser reiniciado se estiver rodando e o Hermes não atualizar suas rotas automaticamente. Neste caso execute `hermes -p infra gateway restart` no perfil do serviço (ou reinicie o backend que atende ao Desktop). O caminho exato depende do seu modo de execução.

Na **primeira abertura**, abra **Skill Manager → Configurações** e escolha a pasta compartilhada. O caminho fica salvo e não precisa ser informado novamente.

## Repositório GitHub (publicação inicial)

O instalador `hermes plugins install` **não cria** um repositório GitHub: ele instala a partir de um repositório já publicado.

Se `https://github.com/inayan60/hermes-skill-manager` ainda não existir, extraia o ZIP e rode uma única vez `PUBLICAR-NO-GITHUB.ps1` em um terminal PowerShell. O publicador usa Git e GitHub CLI (`gh`) e pede autenticação e confirmação de publicação **pública**. Ele se recusa a sobrescrever um repositório já existente.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\PUBLICAR-NO-GITHUB.ps1
```

O código deve estar **na raiz** do GitHub e não dentro de uma subpasta ou ZIP. Depois da publicação basta o comando `hermes ... plugins install ... --enable`.

## O que aparece no Desktop

- **Skill Manager** na barra lateral, com página própria (SDK oficial: `ROUTES_AREA` e `SIDEBAR_NAV_AREA`)
- Entrada **Skill Manager** no menu de comandos
- Configurações próprias em **Settings → Plugins → Skill Manager** (quando suportado)
- **GitHub:** pesquisa repositórios públicos e permite selecionar skills pelos diretórios contendo `SKILL.md`
- **Biblioteca:** pesquisa, categorias, alteração de categoria, atualização com backup e exclusão para lixeira
- **Perfis:** leitura de skills existentes nas pastas padrão, sem alterações
- **CATALOGO-SKILLS.md** e **catalogo.json** gerados na pasta compartilhada para a Lenora consultar

A parte visual foi implementada em JavaScript ESM sem build, usando `@hermes/plugin-sdk` + React do Desktop. O backend é um router FastAPI exposto sob `/api/plugins/hermes-skill-manager/` por `dashboard/plugin_api.py`, conforme documentação oficial.

## Arquivos da distribuição

```text
hermes-skill-manager/
├─ plugin.yaml
├─ __init__.py
├─ desktop/
│  └─ plugin.js
├─ dashboard/
│  ├─ manifest.json
│  └─ plugin_api.py
├─ tests/
│  └─ test_backend.py
├─ .github/workflows/
│  └─ check.yml
├─ PUBLICAR-NO-GITHUB.ps1
├─ after-install.md
└─ README.md
```

## Segurança e limitações

- GitHub **público**, sem credenciais ou tokens; a API anônima tem limites.
- Baixa somente os arquivos da skill selecionada e recursos em seu diretório, não o restante do repositório. Verifica conteúdo pelo hash dos blobs Git; nenhuma skill é executada.
- O plugin roda com os privilégios do Hermes e **não está em sandbox**. Revise a origem antes de instalar.
- A pasta da biblioteca precisa ser acessível **à máquina do gateway**, que pode ser diferente da máquina do Desktop.
- A interface Desktop compartilhada é app-level; o backend fica no perfil selecionado. Portanto, acesse o perfil habilitado ao usar a página.
- Mudanças de arquivo no backend podem exigir reinício da aplicação que hospeda as rotas.
- `--enable` ativa a parte Agent, mas **não garante a ativação da parte Desktop**. Essa é uma limitação intencional de segurança do Hermes.
- As funções de importação, categoria, atualização, backup e remoção foram testadas offline; o carregamento real pelo Hermes Desktop no Windows **não foi testado** neste ambiente.

## Testes

```bash
python -m pytest -q tests/test_backend.py
node --check desktop/plugin.js
```

Quando houver um Hermes 0.22.7 disponível na máquina local:

```powershell
hermes plugins doctor .
hermes plugins validate .
```

## Documentação do Hermes consultada (v0.22.7)

- [Desktop Plugin SDK](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/website/docs/developer-guide/desktop-plugin-sdk.md)
- [Plugins (CLI e `--enable`)](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/website/docs/user-guide/features/plugins.md)
- [Perfis (`-p`)](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/website/docs/reference/profile-commands.md)