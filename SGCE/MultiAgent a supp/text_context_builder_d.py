# -*- coding: utf-8 -*-
import json, re
from pathlib import Path

BASE_DIR = Path(r"C:\Users\Lamis\Desktop\Projet memoire\TRACE\OCR vers LLM\Reduction_hallucinations")
M = BASE_DIR / "MultiAgent"
QUEUE = M / "queues" / "agent_d_queue.json"
OUT = M / "queues" / "agent_d_queue_contextualized.json"
TEXT_DIRS = [M / "Sortie_Textes_Brut_MistralSmall4"]

def load_json(p):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

def norm_name(x):
    x = Path(x).stem.lower()
    for s in ("_trace_sepsis_v1.6-v6.5-selective_precision","_trace_sepsis_v1.6","_trace_sepsis","_mistral","_qwen","_brut"):
        x = x.replace(s, "")
    return re.sub(r"[^a-z0-9]+", "", x)

def page_number(item):
    blob = json.dumps(item, ensure_ascii=False)
    m = re.search(r"\bP(\d+)_E\d+\b", blob)
    if m:
        return int(m.group(1))
    for obj in (item, item.get("symbolic_candidate") or {}):
        for k in ("page","page_number"):
            if obj.get(k) is not None:
                try:
                    return int(obj[k])
                except Exception:
                    pass
    return None

def split_pages(text):
    pats = [
        r"\n\s*={3,}\s*PAGE\s+(\d+)\s*={3,}\s*\n",
        r"\n\s*-{3,}\s*PAGE\s+(\d+)\s*-{3,}\s*\n",
        r"\n\s*\[?PAGE\s+(\d+)\]?\s*\n",
        r"\n\s*===\s*Page\s+(\d+)\s*===\s*\n",
    ]
    for pat in pats:
        ms = list(re.finditer(pat, text, re.I))
        if ms:
            pages = {}
            for i, m in enumerate(ms):
                end = ms[i+1].start() if i+1 < len(ms) else len(text)
                pages[int(m.group(1))] = text[m.end():end].strip()
            return pages
    if "\f" in text:
        return {i+1:v.strip() for i,v in enumerate(text.split("\f")) if v.strip()}
    return {1:text.strip()}

def main():
    q = load_json(QUEUE)
    txt_files=[]
    for d in TEXT_DIRS:
        if d.exists():
            txt_files += list(d.rglob("*.txt"))

    out=[]
    found=pages_found=fallback=missing=0

    for item in q:
        doc=item.get("document") or ""
        target=norm_name(doc)
        matches=[p for p in txt_files if norm_name(p.name)==target]
        if not matches:
            matches=[p for p in txt_files if target in norm_name(p.name) or norm_name(p.name) in target]
        p=matches[0] if len(matches)==1 else None
        pn=page_number(item)
        ctx={"text_file":None,"page_number":pn,"page_text":"","text_available":False,"used_global_text_fallback":False}

        if p:
            found+=1
            txt=p.read_text(encoding="utf-8",errors="ignore")
            pages=split_pages(txt)
            if pn in pages and len(pages)>1:
                ctx["page_text"]=pages[pn]; pages_found+=1
            elif len(pages)==1:
                ctx["page_text"]=next(iter(pages.values())); ctx["used_global_text_fallback"]=True; fallback+=1
            else:
                ctx["page_text"]="\n".join(pages.values()); ctx["used_global_text_fallback"]=True; fallback+=1
            ctx["text_file"]=str(p)
            ctx["text_available"]=bool(ctx["page_text"].strip())
        else:
            missing+=1

        x=dict(item); x["text_context"]=ctx; out.append(x)

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")

    print("="*96)
    print("TRACE / SGCE - TEXT CONTEXT BUILDER D")
    print("="*96)
    print(f"Cas Agent D                      : {len(q)}")
    print(f"Fichiers texte dÃ©couverts        : {len(txt_files)}")
    print(f"Documents texte retrouvÃ©s        : {found}")
    print(f"Pages retrouvÃ©es explicitement   : {pages_found}")
    print(f"Fallback texte global            : {fallback}")
    print(f"Documents texte manquants        : {missing}")
    print(f"\nSortie                           : {OUT}")
    print("\nAucune donnÃ©e clinique n'a Ã©tÃ© modifiÃ©e.")

if __name__=="__main__":
    main()

