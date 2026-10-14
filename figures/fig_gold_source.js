const fs=require('fs');
const C={navy:'#1f3a5f',green:'#2e7d5b',orange:'#c0671a',ofill:'#fbf0e3',gfill:'#eef3f9',txt:'#1d2733'};
let s=[];
const esc=t=>t.replace(/&/g,'&amp;').replace(/</g,'&lt;');
function box(x,y,w,h,stroke,fill,sw=2.2){s.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="${fill}" stroke="${stroke}" stroke-width="${sw}"/>`);}
function text(x,y,t,o={}){s.push(`<text x="${x}" y="${y}" font-size="${o.size||15}" font-weight="${o.bold?700:400}" fill="${o.color||C.txt}" ${o.anchor?`text-anchor="${o.anchor}"`:''} ${o.italic?'font-style="italic"':''} ${o.ls?`letter-spacing="${o.ls}"`:''}>${esc(t)}</text>`);}
function bullets(x,y,items,o={}){let yy=y;for(const it of items){const lines=Array.isArray(it)?it:[it];lines.forEach((l,i)=>{text(x+(i?14:0),yy,(i?'':'• ')+l,o);yy+=o.lh||22;});yy+=o.gap??6;}}
function arrow(x1,y1,x2,y2,color,dash=false){s.push(`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="2.2" ${dash?'stroke-dasharray="6 5"':''} marker-end="url(#m${color.slice(1)})"/>`);}
// défs
const marks=[C.navy,C.green,C.orange,'#7a8796','#3d4b5c'].map(c=>`<marker id="m${c.slice(1)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`).join('');
// --- haut ---
box(36,70,460,150,C.orange,C.ofill);
text(56,104,'Validation médicale du guideline',{bold:true,size:16.5,color:'#8a4510'});
bullets(56,140,['Pr N. Heming, médecine intensive–réanimation','Catégories, vocabulaires, relations, règles'],{size:14.5,gap:10});
box(536,70,944,150,C.navy,C.gfill);
text(556,104,'Guideline TRACE-Sepsis v1.6',{bold:true,size:16.5,color:C.navy});
bullets(556,140,['20 types d’entités cliniques + métadonnées de traçabilité  •  32 relations en 8 familles (signatures verrouillées)','Règles : ancrage documentaire, négation, incertitude, temporalité, valeurs et unités'],{size:14.5,gap:10});
arrow(496,145,534,145,C.orange);
// --- étapes ---
const Y=330,H=300,W=214;
const xs=[36,284,532,780,1028,1276,1524];
const steps=[
 {t:['Corpus'],c:C.navy,f:'#fff',b:['246 dossiers PDF scannés',['Cohorte APROCCHSS','(AP-HP)'],['Réanimation, Hôpital','Raymond-Poincaré'],'2008–2015',['Pseudonymisation','partielle (AP-HP)']]},
 {t:['Sous-corpus'],c:C.navy,f:'#fff',b:['49 dossiers (≈ 20 %)','291 pages',['4 à 8 pages par dossier','(moyenne 5,9)']]},
 {t:['Annotation'],c:C.green,f:'#fff',b:['Label Studio',['Page = unité','de tâche'],'Entités + relations','Annotation manuelle']},
 {t:['Contrôle et','consolidation'],c:C.green,f:'#fff',b:['Labels, frontières',['Signatures','domaine → portée'],['Négation, inférences','non supportées'],'Fusion par dossier','Provenance']},
 {t:['Gold Standard','initial'],c:C.green,f:'#fff',b:['Contrôle structurel',['Conformité au','schéma v1.6']]},
 {t:['Validation','médicale'],c:C.orange,f:C.ofill,b:['Pr N. Heming','Confirmer / modifier','Supprimer / ajouter',['Intégration des','corrections']]},
 {t:['Gold Standard','final'],c:C.navy,f:C.navy,b:['Consolidation finale',['Référence unique','de l’évaluation'],['Traçable jusqu’aux','pages sources'],['Indépendant des','modèles évalués']],white:true},
];
steps.forEach((st,i)=>{const x=xs[i];box(x,Y,W,H,st.c,st.f);
 const col=st.white?'#fff':(st.c===C.orange?'#8a4510':C.navy);
 s.push(`<circle cx="${x+26}" cy="${Y+30}" r="14" fill="${st.white?'#fff':st.c}"/>`);
 text(x+26,Y+35.5,String(i+1),{bold:true,size:14.5,color:st.white?C.navy:'#fff',anchor:'middle'});
 st.t.forEach((l,k)=>text(x+50,Y+36+k*21,l,{bold:true,size:16,color:col}));
 const top=Y+36+st.t.length*21+22;
 bullets(x+16,top,st.b,{size:14,lh:20,gap:9,color:st.white?'#fff':C.txt});
 if(i<6) arrow(x+W,Y+H/2,xs[i+1]-2,Y+H/2,'#3d4b5c');
});
// liens guideline <-> étapes
arrow(612,220,612,Y-2,C.navy); text(620,282,'encadre',{italic:true,size:13.5,color:C.navy});
arrow(700,Y,700,222,'#7a8796',true); text(708,262,'cas ambigus',{italic:true,size:13.5,color:'#5a6675'});
arrow(886,220,886,Y-2,C.navy); text(894,282,'référentiel',{italic:true,size:13.5,color:C.navy});
arrow(1383,Y,1383,222,C.orange,true); text(1391,258,'clarification',{italic:true,size:13.5,color:C.orange}); text(1391,276,'des règles',{italic:true,size:13.5,color:C.orange});
// accolades
function brace(x1,x2,label,color){const y=660;s.push(`<path d="M${x1} ${y} v12 H${x2} v-12" fill="none" stroke="${color}" stroke-width="2"/>`);text((x1+x2)/2,y+42,label,{bold:true,size:15,color,anchor:'middle',ls:0.6});}
brace(36,xs[1]+W,'PRÉPARATION DU CORPUS',C.navy);
brace(xs[2],xs[4]+W,'ANNOTATION ET CONTRÔLE',C.green);
brace(xs[5],xs[6]+W,'VALIDATION ET GOLD STANDARD',C.orange);
const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1760 730" width="1760" height="730" font-family="Liberation Sans, DejaVu Sans, Arial, sans-serif"><defs>${marks}</defs><rect width="1760" height="730" fill="#fff"/>${s.join('\n')}</svg>`;
fs.writeFileSync('fig_gold.svg',svg);
fs.writeFileSync('fig.html',`<html><body style="margin:0">${svg}</body></html>`);
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1760,height:730},deviceScaleFactor:2.5});
await p.goto('file://'+process.cwd()+'/fig.html');await p.screenshot({path:'fig_gold.png',clip:{x:0,y:0,width:1760,height:730}});
await p.pdf({path:'fig_gold.pdf',width:'1760px',height:'730px',printBackground:true,pageRanges:'1'});await b.close();})();
