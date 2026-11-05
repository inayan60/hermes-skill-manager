import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
const source = readFileSync(new URL('../desktop/plugin.js', import.meta.url), 'utf8')
const stripped = source.replace(/^import React from 'react'\s*$/m,'')
  .replace(/^import \{ ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, host \} from '@hermes\/plugin-sdk'\s*$/m,'')
  .replace('export default {','const plugin = {')
assert.notEqual(stripped, source, 'expected ESM input')
const handlers=[];let settings=0
const ctx={rest:async()=>({}),registerSettingsPage:()=>settings++,registerMany:xs=>handlers.push(...xs)}
const React={createElement:()=>({}),useState:()=>[],useMemo:()=>[],useEffect:()=>{}}
const plugin=Function('React','ROUTES_AREA','SIDEBAR_NAV_AREA','PALETTE_AREA','host',
  stripped+'\nreturn plugin;')(React,'routes','sidebar.nav','palette',{navigate:()=>{}})
assert.equal(plugin.id,'hermes-skill-manager')
plugin.register(ctx)
assert.equal(settings,1)
assert.equal(handlers.find(x=>x.area==='routes')?.data.path,'/skill-manager')
assert.equal(handlers.find(x=>x.area==='sidebar.nav')?.data.path,'/skill-manager')
console.log('Desktop plugin registered route + sidebar + settings')