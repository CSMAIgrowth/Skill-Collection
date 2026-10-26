import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

function attr(tag,name){return tag.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1]??null;}

// Static risk checks only: actual focus scrolling, computed colors and column geometry
// require browser evidence and are deliberately never marked verified by this module.
export function checkManagedGroupHtml(artifact){
 const checks=[];
 const add=(sample,status,message)=>checks.push({sample,status,message});
 let controls=0,rankings=0;
 const htmlBlocks=(artifact.manifest?.blocks??[]).filter(b=>b.type==='html');
 for(const block of htmlBlocks){
  const html=block.body??block.html??'';
  if(html.includes('data-card-scope=')){
   for(const site of ['all','UK','DE','US']){
    const root=`.page-analysis:has(#site-${site}:checked)`;
    const hides=html.includes(`${root} .card-store-options:not([data-card-scope="${site}"]){display:none!important}`);
    const shows=html.includes(`${root} .card-store-options[data-card-scope="${site}"]{display:flex!important}`);
    add('HTML-007',hides&&shows?'passed':'failed',`${block.id}/${site}: show only the selected site's store controls despite shared chips styles`);
   }
  }
  const inputs=[...html.matchAll(/<input\b[^>]*>/g)].map(m=>m[0])
   .filter(tag=>attr(tag,'type')==='radio'&&['site','sort'].includes(attr(tag,'name')));
  const labels=[...html.matchAll(/<label\b([^>]*)>([\s\S]*?)<\/label>/g)];
  if(!inputs.length){add('HTML-001','not_applicable',`${block.id}: no site/sort radio controls`);}
  for(const tag of inputs){
   controls++;
   const id=attr(tag,'id');
   const matches=labels.filter(m=>attr('<label '+m[1]+'>','for')===id);
   // Store navigation labels intentionally focus the remote card-area control.
   // Require exactly one local owning label; any extra labels must be explicit navigation.
   const owners=matches.filter(m=>[...m[2].matchAll(/<input\b[^>]*>/g)].some(x=>attr(x[0],'id')===id));
   const remoteAllowed=matches.filter(m=>!owners.includes(m)).every(m=>/\bstore-site-jump\b/.test(attr('<label '+m[1]+'>','class')??''));
   const label=owners.length===1&&remoteAllowed?owners[0]:null;
   const inputInLabel=!!label&&[...label[2].matchAll(/<input\b[^>]*>/g)].some(m=>attr(m[0],'id')===id);
   const localPosition=/\.chips\s+label\s*\{[^}]*position\s*:\s*relative/.test(html)
    &&/\.chips\s+label\s*>\s*\.switch\s*\{[^}]*position\s*:\s*absolute/.test(html);
   add('HTML-001',inputInLabel&&localPosition?'passed':'failed',`${block.id}/${id}: focus control inside associated label with local positioning`);
   const visibleText=label?.[2].replace(/<[^>]*>/g,'').trim();
   const nestedSpan=!!label&&/<span\b/.test(label[2]);
   const whiteSpanRule=/\.chips\s+span[^{}]*\{[^}]*background\s*:\s*(?:#fff(?:fff)?\b|white\b)/i.test(html);
   add('HTML-002',visibleText&&!(nestedSpan&&whiteSpanRule)?'passed':'failed',`${block.id}/${id}: readable text node, no known inherited white chip layer`);
  }
  const tables=[...html.matchAll(/<table\b[^>]*class="[^"]*\branking\b[^"]*"[^>]*>([\s\S]*?)<\/table>/g)];
  if(!tables.length){add('HTML-003','not_applicable',`${block.id}: no ranking tables`);}
  const tracks=[];
  for(const [index,table] of tables.entries()){
   rankings++;
   const columns=[...(table[1].match(/<colgroup>([\s\S]*?)<\/colgroup>/)?.[1]??'').matchAll(/<col\b[^>]*style="[^"]*width:\s*([\d.]+)%[^\"]*"[^>]*>/g)].map(m=>Number(m[1]));
   const headCount=(table[1].match(/<thead>([\s\S]*?)<\/thead>/)?.[1].match(/<th\b/g)??[]).length;
   const fixed=/table\.ranking\s*\{[^}]*table-layout\s*:\s*fixed/.test(html);
   const widthsValid=columns.length===headCount&&columns.length>0&&Math.abs(columns.reduce((n,v)=>n+v,0)-100)<0.01;
   add('HTML-003',fixed&&widthsValid?'passed':'failed',`${block.id}/ranking-${index+1}: fixed layout and explicit column tracks match headers and total 100%`);
   tracks.push(JSON.stringify(columns));
  }
  if(tables.length>1)add('HTML-003',new Set(tracks).size===1?'passed':'failed',`${block.id}: sort views share identical column tracks`);
 }
 const failures=checks.filter(c=>c.status==='failed');
 return {status:failures.length?'failed':'static_passed_browser_pending',scope:'static-only',blocksChecked:htmlBlocks.length,controlsChecked:controls,rankingTablesChecked:rankings,checks,failures:failures.length,browserVerification:'not_run'};
}

const calledAsCli=process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url);
if(calledAsCli){
 const inputIndex=process.argv.indexOf('--input');
 if(inputIndex<0||!process.argv[inputIndex+1])throw new Error('Usage: node check-managed-group-html.mjs --input <artifact.json>');
 const artifact=JSON.parse(fs.readFileSync(process.argv[inputIndex+1],'utf8'));
 const result=checkManagedGroupHtml(artifact);
 console.log(JSON.stringify(result,null,2));
 if(result.failures)process.exitCode=1;
}
