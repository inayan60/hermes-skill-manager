import React from 'react'
import { ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, host } from '@hermes/plugin-sdk'

const h = React.createElement
const { useState, useEffect, useMemo } = React
const COLORS = {
  text: 'var(--ui-text-primary, #e5e8ec)', muted: 'var(--ui-text-secondary, #9da5b0)',
  bg: 'var(--ui-bg-primary, transparent)', raised: 'var(--ui-bg-secondary, rgba(150,150,150,.07))',
  border: 'var(--ui-border, rgba(140,140,140,.25))', accent: 'var(--ui-accent, #6c99eb)'
}
const base = { color: COLORS.text, fontSize: 13 }
const inputStyle = { ...base, background: 'var(--ui-input-bg, rgba(120,120,120,.08))', border: `1px solid ${COLORS.border}`,
  borderRadius: 7, padding: '9px 10px', outline: 'none', minWidth: 0, flex: 1 }
const btnStyle = { ...base, border: `1px solid ${COLORS.border}`, borderRadius: 7, padding: '8px 12px',
  background: COLORS.raised, cursor: 'pointer', whiteSpace: 'nowrap' }
const actionStyle = { ...btnStyle, background: 'var(--ui-accent, #4778d9)', color: 'white', borderColor: 'transparent' }
const cardStyle = { border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 14,
  background: COLORS.raised, display: 'flex', flexDirection: 'column', gap: 8 }
const line = { display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8 }
const label = { fontSize: 11, color: COLORS.muted, display: 'block', marginBottom: 5 }
const muted = { fontSize: 12, color: COLORS.muted }
const badgeStyle = { border: `1px solid ${COLORS.border}`, padding: '2px 7px', borderRadius: 12, color: COLORS.muted, fontSize: 11 }
const defaultCategories = ['Geral', 'Desenvolvimento', 'Infraestrutura', 'Segurança', 'Pesquisa', 'Documentação', 'Automação', 'Outros']

function Button({ children, onClick, primary=false, disabled=false, title='', style={} }) {
  return h('button', { type: 'button', title, disabled, onClick,
    style: { ...(primary ? actionStyle : btnStyle), opacity: disabled ? .48 : 1, cursor: disabled ? 'not-allowed' : 'pointer', ...style } }, children)
}
function Input({value,onChange,placeholder='',style={}}) {
  return h('input', { type: 'text', value, placeholder,
    onChange: e=>onChange(e.target.value), style: { ...inputStyle, ...style } })
}
function Panel({title,children,subtitle}) {
  return h('section', {style:cardStyle},
    h('div', null, h('div', {style:{fontWeight:650, fontSize:15}}, title),
      subtitle && h('p',{style:{...muted,margin:'5px 0 0'}},subtitle)), children)
}
function Pill({children}) { return h('span',{style:badgeStyle},children) }
function Notice({error,message}) {
  if (!error && !message) return null
  return h('div',{role:'status',style:{padding:'10px 12px',borderRadius:8,
    border:`1px solid ${COLORS.border}`,color:error?'#dc8a8a':COLORS.text,
    background:COLORS.raised,whiteSpace:'pre-wrap'}},error || message)
}
function Tab({name,active,onClick}) {
  return h(Button,{onClick, style:{fontWeight:active?700:400,
    borderColor:active?COLORS.accent:COLORS.border,
    background:active?'var(--ui-accent-muted, rgba(100,140,220,.14))':COLORS.raised}}, name)
}

function SkillManager({request, initialTab='discover'}) {
  const [tab,setTab]=useState(initialTab)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const [settings,setSettings]=useState({library_dir:'',hermes_dir:''})
  const [library,setLibrary]=useState([])
  const [libraryReady,setLibraryReady]=useState(false)
  const [repo,setRepo]=useState('')
  const [scan,setScan]=useState(null)
  const [chosen,setChosen]=useState({})
  const [filter,setFilter]=useState('')
  const [cat,setCat]=useState('Todas')
  const [preview,setPreview]=useState(null)
  const [profiles,setProfiles]=useState(null)

  async function call(path,body) {
    return request(path,body===undefined?undefined:{method:'POST',body,timeoutMs:120000})
  }
  async function load() {
    const d=await call('/state')
    setSettings(d.settings || {library_dir:'',hermes_dir:''})
    setLibrary(d.library || [])
    setLibraryReady(Boolean(d.configured))
  }
  useEffect(()=>{let alive=true; call('/state').then(d=>{if(alive){setSettings(d.settings||{});
      setLibrary(d.library||[]);setLibraryReady(Boolean(d.configured))}})
    .catch(e=>{if(alive) setError('Backend indisponível. Habilite a parte Agent do plugin e reinicie o gateway.\n'+String(e))});
    return()=>{alive=false}},[])
  async function run(fn,ok='') {
    setBusy(true);setError('');setMessage('')
    try { await fn(); if(ok) setMessage(ok) }
    catch(e){setError(e?.message || String(e))}
    finally {setBusy(false)}
  }
  const categories = useMemo(()=>Array.from(new Set([...defaultCategories,...library.map(x=>x.category).filter(Boolean),
    ...(scan?.skills||[]).map(x=>x.category).filter(Boolean)])).sort((a,b)=>a.localeCompare(b)),[library,scan])
  const installedIds = useMemo(()=>new Set(library.map(x=>x.id)),[library])
  const found = useMemo(()=> (scan?.skills||[]).filter(x=>{
    const match=(x.name+' '+x.description+' '+x.path).toLowerCase().includes(filter.toLowerCase())
    return match && (cat==='Todas' || x.category===cat)
  }),[scan,filter,cat])
  const stocked = useMemo(()=>library.filter(x=>{
    return (x.name+' '+x.description+' '+x.repository).toLowerCase().includes(filter.toLowerCase()) &&
      (cat==='Todas' || x.category===cat)
  }),[library,filter,cat])
  const selectedCount=Object.values(chosen).filter(Boolean).length
  async function openPreview(skill) {
    await run(async()=>{
      if (!scan) return
      const d=await call('/preview',{scan_id:scan.scan_id,path:skill.path})
      setPreview({title:skill.name,body:d.content})
      setScan(old=>({...old,skills:old.skills.map(x=>x.path===skill.path?d.item:x)}))
    })
  }
  async function addSelected() {
    const items = (scan?.skills||[]).filter(x=>chosen[x.path]).map(x=>({path:x.path,category:x.category||'Geral'}))
    if(!items.length) return
    if(items.length > 50) { setError('Instale no máximo 50 skills por operação.'); return }
    await run(async()=>{
      const d=await call('/install',{scan_id:scan.scan_id,items})
      setLibrary(d.library||[]);setChosen({});setLibraryReady(true)
    }, `${items.length} skill(s) adicionada(s) à biblioteca. Nenhum perfil foi alterado.`)
  }
  async function changeCategory(item,v) {
    await run(async()=>{const d=await call('/category',{id:item.id,category:v});setLibrary(d.library||[])},'Categoria atualizada.')
  }
  async function updateItem(item) {
    await run(async()=>{const d=await call('/update',{id:item.id});setLibrary(d.library||[])},'Skill atualizada, com backup do conteúdo anterior.')
  }
  async function removeItem(item) {
    if (!window.confirm(`Mover "${item.name}" para a lixeira da biblioteca?`)) return
    await run(async()=>{const d=await call('/remove',{id:item.id});setLibrary(d.library||[])},'Skill movida para .lixeira.')
  }
  function categoryChooser(item) {
    return h('select',{value:item.category||'Geral',onChange:e=>changeCategory(item,e.target.value),
      disabled:busy,style:{...inputStyle,flex:'0 1 165px',padding:6}}, categories.map(x=>h('option',{key:x,value:x},x)))
  }
  const searchRow = h('div',{style:line},
    h(Input,{value:filter,onChange:setFilter,placeholder:'Buscar nome, descrição ou origem…'}),
    h('select',{value:cat,onChange:e=>setCat(e.target.value),style:{...inputStyle,flex:'0 1 170px'}},
      ['Todas',...categories].map(x=>h('option',{key:x,value:x},x))))

  return h('div',{style:{...base,padding:'18px clamp(12px, 3vw, 32px)',height:'100%',overflow:'auto',background:COLORS.bg}},
    h('div',{style:{...line,justifyContent:'space-between',marginBottom:12}},
      h('div',null,h('h1',{style:{fontSize:23,fontWeight:750,margin:'0 0 5px'}},'Skill Manager'),
        h('div',{style:muted},'Biblioteca compartilhada • Curadoria • Sem ativar skills nos bots')),
      h(Pill,null,`${library.length} na biblioteca`)),
    h('div',{style:{...line,marginBottom:16}},
      h(Tab,{name:'GitHub',active:tab==='discover',onClick:()=>{setTab('discover');setFilter('');setCat('Todas')}}),
      h(Tab,{name:'Biblioteca',active:tab==='library',onClick:()=>{setTab('library');setFilter('');setCat('Todas')}}),
      h(Tab,{name:'Perfis (leitura)',active:tab==='profiles',onClick:()=>setTab('profiles')}),
      h(Tab,{name:'Configurações',active:tab==='settings',onClick:()=>setTab('settings')})),
    h(Notice,{error,message}),
    !libraryReady && tab!=='settings' && h('div',{style:{...cardStyle,margin:'12px 0'}},
      'Biblioteca ainda não configurada. Defina uma pasta compartilhada em Configurações.',
      h(Button,{onClick:()=>setTab('settings')},'Configurar pasta')),
    tab==='discover' && h('div',{style:{display:'grid',gap:12,marginTop:12}},
      h(Panel,{title:'Descobrir skills no GitHub',subtitle:'Informe um repositório público. Apenas os arquivos das skills selecionadas serão baixados.'},
        h('div',{style:line},
          h(Input,{value:repo,onChange:setRepo,placeholder:'dono/repositório ou https://github.com/dono/repositório'}),
          h(Button,{primary:true,disabled:busy||!repo.trim(),onClick:()=>run(async()=>{
            const d=await call('/discover',{repository:repo});setScan(d);setChosen({});setFilter('');setCat('Todas');setPreview(null)
          },'Pesquisa concluída. Marque apenas as skills que deseja importar.')},busy?'Aguarde…':'Analisar'))),
      scan && h(Panel,{title:`${scan.skills.length} skills em ${scan.repository}`,subtitle:`Commit fixado: ${scan.commit.slice(0,12)} • ${scan.note||'Selecione as skills desejadas.'}`},
        searchRow,
        h('div',{style:{...line,justifyContent:'space-between'}},
          h('div',{style:muted},`${found.length} resultados • ${selectedCount} selecionadas`),
          h('div',{style:line},
            h(Button,{disabled:busy,onClick:()=>setChosen(Object.fromEntries(found.slice(0,50).map(x=>[x.path,true])))},'Marcar até 50'),
            h(Button,{disabled:busy,onClick:()=>setChosen({})},'Limpar'),
            h(Button,{primary:true,disabled:busy||!selectedCount||!libraryReady,
              onClick:addSelected},`Adicionar (${selectedCount})`))),
        ...found.slice(0,200).map(x=>h('div',{key:x.path,style:{...line,borderBottom:`1px solid ${COLORS.border}`,padding:'9px 0'}},
          h('input',{type:'checkbox',checked:!!chosen[x.path],disabled:busy,
            onChange:e=>setChosen(o=>Object.values(o).filter(Boolean).length>=50 && e.target.checked ? o : ({...o,[x.path]:e.target.checked}))}),
          h('div',{style:{flex:1,minWidth:170}},
            h('div',{style:{fontWeight:600}},x.name, installedIds.has(x.installed_key) ? ' • já na biblioteca' : ''),
            h('div',{style:muted},(x.description||'Sem descrição')+' • '+x.path)),
          h(Pill,null,x.category||'Geral'),h(Button,{disabled:busy,onClick:()=>openPreview(x)},'Prévia'))),
        found.length>200 && h('p',{style:muted},'Mostrando os primeiros 200 resultados; refine a busca para encontrar outros.'))),
    tab==='library' && h('div',{style:{display:'grid',gap:12,marginTop:12}},
      h(Panel,{title:'Skills da biblioteca',subtitle:'As skills daqui não estão automaticamente habilitadas em nenhum bot.'},
        h('div',{style:{...line,marginBottom:6}},h(Button,{disabled:busy,onClick:()=>run(load,'Lista atualizada.')},'Recarregar'),
          h(Pill,null,`${stocked.length} encontradas`)),
        searchRow,
        ...stocked.slice(0,250).map(x=>h('div',{key:x.id,style:{borderBottom:`1px solid ${COLORS.border}`,padding:'10px 0'}},
          h('div',{style:{...line,justifyContent:'space-between'}},
            h('div',{style:{flex:1,minWidth:200}},
              h('strong',null,x.name),h('div',{style:muted},x.repository+' / '+x.repo_path),
              h('div',{style:muted},`${x.file_count} arquivos • ${x.commit.slice(0,10)} • ${x.relative_dir}`)),
            categoryChooser(x),h(Button,{disabled:busy,onClick:()=>updateItem(x)},'Atualizar'),
            h(Button,{disabled:busy,onClick:()=>removeItem(x)},'Remover')))),
        !stocked.length && h('p',{style:muted},'Nenhuma skill encontrada.'))),
    tab==='profiles' && h('div',{style:{display:'grid',gap:12,marginTop:12}},
      h(Panel,{title:'Skills instaladas nos perfis Hermes',subtitle:'Consulta local, somente leitura. A estrutura varia conforme a instalação.'},
        h(Button,{disabled:busy,onClick:()=>run(async()=>setProfiles(await call('/profiles')))},'Pesquisar perfis'),
        profiles && h('div',{style:{display:'grid',gap:10}},
          h('div',{style:muted},profiles.note),
          ...profiles.profiles.map(x=>h('div',{key:x.profile,style:{...cardStyle,gap:6}},
            h('strong',null,`${x.profile}: ${x.count} skills`),
            h('div',{style:{...muted,maxHeight:120,overflow:'auto'}},x.sample.join(' • '))))))),
    tab==='settings' && h('div',{style:{display:'grid',gap:12,marginTop:12}},
      h(Panel,{title:'Pasta compartilhada',subtitle:'Salva no computador onde o gateway Hermes está rodando, permanecendo entre execuções.'},
        h('label',null,h('span',{style:label},'Biblioteca de skills (caminho absoluto ou pasta UNC)'),
          h(Input,{value:settings.library_dir||'',onChange:v=>setSettings(s=>({...s,library_dir:v})),
            placeholder:'C:\\HermesSkills ou \\\\servidor\\compartilhamento\\skills',style:{width:'100%'}})),
        h('label',null,h('span',{style:label},'Instalação Hermes para inventário somente leitura'),
          h(Input,{value:settings.hermes_dir||'',onChange:v=>setSettings(s=>({...s,hermes_dir:v})),
            style:{width:'100%'}})),
        h('div',{style:line},h(Button,{primary:true,disabled:busy,
          onClick:()=>run(async()=>{const d=await call('/settings',settings);setSettings(d.settings);setLibrary(d.library);
            setLibraryReady(d.configured)},'Configurações salvas. Biblioteca pronta.')},'Salvar configurações')),
        h('p',{style:muted},'A biblioteca armazena skills e gera catalogo.json e CATALOGO-SKILLS.md. Não há alteração de profiles, tools ou providers.'))),
    preview && h('div',{role:'dialog','aria-label':'Prévia SKILL.md',style:{position:'fixed',inset:0,zIndex:5000,
      background:'rgba(0,0,0,.7)',display:'flex',alignItems:'center',justifyContent:'center',padding:20}},
      h('div',{style:{...cardStyle,background:'var(--ui-bg-primary, #1f2329)',width:'min(850px, 95vw)',maxHeight:'85vh',overflow:'hidden'}},
        h('div',{style:{...line,justifyContent:'space-between'}},h('strong',null,preview.title),
          h(Button,{onClick:()=>setPreview(null)},'Fechar')),
        h('p',{style:muted},'Prévia não equivale a auditoria de segurança. Arquivos baixados não são executados.'),
        h('pre',{style:{whiteSpace:'pre-wrap',overflow:'auto',fontFamily:'monospace',fontSize:12}},preview.body))))
  )
}

export default {
  id: 'hermes-skill-manager',
  name: 'Hermes Skill Manager',
  description: 'Curadoria visual de skills de repositorios GitHub, biblioteca compartilhada e catalogo para agentes',
  defaultEnabled: true,
  register(ctx) {
    const request=(p,o)=>ctx.rest(p,o)
    // Opcional e nativo: preferências dentro de Settings > Plugins.
    // Não altera as opções de ativação; elas são controladas pelo Hermes.
    ctx.registerSettingsPage?.({
      id:'settings', title:'Skill Manager', icon:'library',
      render:()=>h(SkillManager,{request,initialTab:'settings'})
    })
    ctx.registerMany([
      {id:'page',area:ROUTES_AREA,title:'Skill Manager',data:{path:'/skill-manager'},
        render:()=>h(SkillManager,{request})},
      {id:'navigation',area:SIDEBAR_NAV_AREA,order:77,
        data:{path:'/skill-manager',label:'Skill Manager',codicon:'library'}},
      {id:'open',area:PALETTE_AREA,
        data:{id:'skill-manager.open',label:'Abrir Skill Manager',keywords:['skill','biblioteca','github'],
          run:()=>host.navigate('/skill-manager')}}
    ])
  }
}