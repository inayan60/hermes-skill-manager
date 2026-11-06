# Hermes Skill Manager v1.4.0

Plugin nativo (Agent + Desktop) para **Hermes 0.22.7**, com descoberta seletiva de skills no GitHub, biblioteca compartilhada e **habilitação individual por perfil** sem duplicação de arquivos nem ferramentas de IA.

## Instalação / atualização

```powershell
# Já instalado no perfil jobson:
hermes -p jobson plugins update hermes-skill-manager

# Primeira instalação:
hermes -p jobson plugins install inayan60/hermes-skill-manager --enable
```

O Desktop carrega a página **Skill Manager** da barra lateral. Depois da atualização, use **Capabilities → Plugins → Rescan** ou reinicie o Desktop se estiver usando cópia antiga. A parte **Desktop** tem habilitação independente da parte Agent no Hermes. O gateway/backend pode precisar reiniciar para registrar as novas rotas HTTP.

## Configuração inicial

Abra **Skill Manager → Configurações** e informe `C:\Hermes-Skills\skills` (ou o caminho onde estão suas skills). Esse caminho é salvo no LocalAppData do host do backend; não é necessário repetir a configuração. São suportadas tanto pastas `.../Hermes-Skills` que contêm `skills/` quanto a própria pasta `.../Hermes-Skills/skills`. As skills existentes são inventariadas fisicamente pelos arquivos `SKILL.md` mesmo se não constarem em `catalogo.json`.

Na aba **Perfis**:

1. Selecione um perfil existente no Hermes, por exemplo `arthur-jenkins`.
2. Localize cada skill por nome ou caminho hierárquico.
3. Para uma skill ainda não revisada, abra **Prévia / Aprovar**, leia os arquivos e confirme a revisão manual. A interface apresenta `SKILL.md`; a aprovação é vinculada ao hash do conteúdo **de toda a pasta da skill** (incluindo scripts e outros arquivos). Não se trata de auditoria automática.
4. Clique em **Habilitar**. O plugin acrescenta **somente o diretório daquela skill** a `skills.external_dirs` do perfil, e retira seu nome de `skills.disabled` caso estivesse desabilitada.
5. **Desabilitar** adiciona o nome a `skills.disabled`, preservando a associação. **Desassociar** remove a referência individual de `skills.external_dirs` sem excluir nenhum arquivo, quando houver associação individual.

O plugin **nunca associa uma pasta de repositório inteiro automaticamente**. Skills filhas de outras skills são detectadas; associar uma pasta que também expõe outras skills é bloqueado. Se uma associação usa um diretório ancestral, a interface informa **Via diretório ancestral**. Use **Sincronizar vínculos** para eliminar a exposição ampla sem alterar os vínculos individuais.

### Sincronização de catálogo e permissões (v1.4.0)

Na aba **Perfis**, selecione um profile e clique em **Sincronizar vínculos**.
O Skill Manager apresenta uma prévia e solicita confirmação antes de alterar a configuração.
A operação remove de `skills.external_dirs` apenas raízes compartilhadas/ancestrais
que expõem skills da biblioteca indiretamente. **Mantém** os vínculos individuais,
`skills.disabled`, outras fontes de skills, os arquivos da biblioteca e os demais profiles.
É idempotente; uma segunda execução não precisa fazer alterações.

**Migração conservadora:** as skills que eram expostas exclusivamente por um
diretório ancestral deixam de estar disponíveis. Habilite explicitamente no
profile apenas as desejadas, usando Prévia/Aprovar e Habilitar. Uma skill nova
adicionada à biblioteca não será ativada automaticamente após a remoção da raiz
ampla. Não é uma operação agendada nem um watcher do sistema de arquivos.

### Estados

| Estado | Significado |
|---|---|
| **Habilitada** | Diretório está presente nos roots externos (direta ou indiretamente), Hermes resolve esta skill e ela não está em `skills.disabled`. |
| **Desabilitada** | Associada, mas seu nome está em `skills.disabled` do perfil. |
| **Pendente de revisão** | Não associada e ainda não aprovada para habilitação. |
| **Não associada** | Aprovada no catálogo, mas não associada ao perfil escolhido. |
| **Conflito** | Diretório exposto, porém a resolução nativa identifica nome ambíguo/sobreposto. |

Uma skill já associada em outro momento pode aparecer como **Habilitada · Não revisada**: a falta de aprovação não altera perfis existentes automaticamente.

### Persistência e atualização centralizada

As relações são persistidas **pelo Hermes**, no `config.yaml` de cada perfil, em `skills.external_dirs` e `skills.disabled`. Não existe cópia nem banco de vínculos paralelo. As aprovações de revisão são salvas em `.hsm-reviews.json` na biblioteca, independentes dos perfis. Uma alteração de qualquer arquivo da skill invalida a aprovação daquela revisão, mas não muda as associações existentes. Ao atualizar a skill na biblioteca, todos os perfis que apontam para o mesmo diretório passam a ver os arquivos atualizados no próximo carregamento; sessões já abertas podem manter um prompt em cache até começar uma nova sessão.

A aba **Biblioteca** conserva a importação GitHub por seleção, categoria, atualizações e backups. A aba **Perfis** é o inventário abrangente de skills existentes no disco (inclusive as inseridas manualmente). A remoção de uma skill catalogada agora é recusada se algum perfil ainda referenciar essa pasta, para evitar referências quebradas.

## Limites e segurança

- O backend usa as APIs nativas de **scope de perfil**, bloqueio de mutação de configuração e `save_config`. O parâmetro de perfil é confrontado com a lista real de `list_profiles`, nunca com um caminho arbitrário vindo do navegador.
- O Hermes prioriza **projeto confiável → perfil local → create_dir → external_dirs**. O plugin consulta o resolvedor nativo para evitar ativar um nome já existente. É possível haver mais restrições por plataforma/ambiente que não se resumem ao estado global da interface.
- A biblioteca é compartilhada, mas não é isolada: skills em `external_dirs` podem ser modificadas por processos autorizados no sistema. Use permissões NTFS para proteger a curadoria. Uma skill aprovada não é necessariamente segura.
- **Não** altera Hindsight, providers, ferramentas ou outros perfis. Não faz chamadas a modelos/IA.
- Instalação pela CLI ativa o Agent; a metade Desktop é ativada pelo switch independente em **Capabilities → Plugins**.
- O backend Hermes e o Desktop não foram executados no Windows deste projeto; os testes são automatizados com scopes nativos simulados. Valide em seu ambiente antes de usar em produção.

## Testes

```bash
python -m pip install fastapi httpx pytest PyYAML
python -m pytest -q tests/
cp desktop/plugin.js /tmp/hsm-plugin.mjs
node --check /tmp/hsm-plugin.mjs
node tests/smoke-desktop.mjs
```

## Estrutura

```text
plugin.yaml
__init__.py
dashboard/manifest.json
dashboard/plugin_api.py
desktop/plugin.js
tests/test_backend.py
tests/test_profiles.py
tests/smoke-desktop.mjs
.github/workflows/check.yml
```

Referências para v0.22.7: [skills externas](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/website/docs/user-guide/features/skills.md#external-skill-directories), [resolvedor](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/agent/skill_utils.py), [toggle nativo](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/hermes_cli/web_routers/skills.py) e [Desktop Plugin SDK](https://github.com/NousResearch/hermes-agent/blob/v0.22.7/website/docs/developer-guide/desktop-plugin-sdk.md).