# Hermes Skill Manager v1.3.0

A parte Agent foi instalada/ativada no perfil escolhido pelo comando `--enable`. Para a interface aparecer, verifique **Capabilities → Plugins → Desktop** (switch independente da parte Agent) e clique em **Rescan**. Se a interface abre mas a API retorna indisponível, reinicie o backend/gateway que atende ao Hermes Desktop.

Em **Skill Manager → Configurações**, informe `C:\Hermes-Skills\skills` e salve uma vez. Na aba **Perfis**, escolha um bot, revise as skills e ative individualmente. As associações são salvas pelo Hermes em `skills.external_dirs`/`skills.disabled`, não há cópias e nenhum outro perfil é modificado.