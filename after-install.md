# Hermes Skill Manager instalado

A parte **Agent** foi instalada. Quando a instalação foi feita com `--enable`, ela fica ativada no perfil selecionado.

Abra o **Hermes Desktop**. O pacote inclui uma página **Skill Manager** na barra lateral e uma entrada em **Settings > Plugins**.

**Caso não apareça**: ative a parte **Desktop** em **Capabilities > Plugins**. O CLI `--enable` não controla diretamente essa opção visual, por design do Hermes. Se a página carregar mas o backend responder indisponível, verifique o perfil conectado e reinicie o serviço do gateway/backend para carregar as rotas.

Na primeira utilização, indique a pasta compartilhada em **Skill Manager > Configurações**. Essa preferência será lembrada.