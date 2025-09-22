from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os, uuid, shutil, re, json
from typing import List

UPLOAD_DIR = '/mnt/data/smart_doc_checker_prototype/uploads'
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title='Smart Doc Checker - Prototype')

# Simple in-memory stores (for prototype/demo)
FILE_STORE = {}   # file_id -> {path, filename}
ANALYSES = {}     # analysis_id -> result
USER_CREDITS = {'demo-user': 10}

@app.post('/upload')
async def upload(files: List[UploadFile] = File(...)):
    if len(files) > 3:
        raise HTTPException(status_code=400, detail='Max 3 files allowed')
    file_ids = []
    for f in files:
        contents = await f.read()
        file_id = str(uuid.uuid4())
        path = os.path.join(UPLOAD_DIR, file_id + '_' + f.filename)
        with open(path, 'wb') as fh:
            fh.write(contents)
        FILE_STORE[file_id] = {'path': path, 'filename': f.filename}
        file_ids.append(file_id)
    return JSONResponse({'file_ids': file_ids})

def extract_text_from_path(path):
    # Very simple text extraction for txt, pdf, docx (best-effort)
    if path.lower().endswith('.txt'):
        return open(path, 'r', encoding='utf-8', errors='ignore').read()
    if path.lower().endswith('.pdf'):
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(path)
            texts = []
            for p in reader.pages:
                texts.append(p.extract_text() or '')
            return '\n'.join(texts)
        except Exception as e:
            return ''
    if path.lower().endswith('.docx'):
        try:
            import docx
            doc = docx.Document(path)
            return '\n'.join(p.text for p in doc.paragraphs)
        except Exception as e:
            return ''
    # fallback
    try:
        return open(path, 'r', encoding='utf-8', errors='ignore').read()
    except:
        return ''

def extract_facts(text):
    facts = []
    # attendance percent
    for m in re.finditer(r'(\battendance\b)[^\n\.!]*?(\d{1,3}%?)', text, flags=re.I):
        facts.append({'type':'attendance', 'value':m.group(2), 'context':m.group(0)})
    # times like 10 PM, midnight
    for m in re.finditer(r'(\b(?:\d{1,2}\s?(?:AM|PM|am|pm)|midnight|noon)\b)', text):
        facts.append({'type':'time', 'value':m.group(1), 'context':m.group(0)})
    # dates (simple)
    for m in re.finditer(r'(\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b)', text):
        facts.append({'type':'date', 'value':m.group(1), 'context':m.group(0)})
    return facts

def mock_llm_contradiction(s1, s2):
    # VERY simple heuristic mock. Replace with real LLM call.
    s1_low = s1.lower(); s2_low = s2.lower()
    # attendance mismatch
    m1 = re.search(r'(\d{1,3}%)', s1_low)
    m2 = re.search(r'(\d{1,3}%)', s2_low)
    if m1 and m2 and m1.group(1) != m2.group(1):
        return {'contradict': True, 'type':'attendance', 'suggestion': f'Standardize attendance to {m1.group(1)} or {m2.group(1)}'}
    # time mismatch
    t1 = re.search(r'(\d{1,2}\s?(?:am|pm)|midnight|noon)', s1_low)
    t2 = re.search(r'(\d{1,2}\s?(?:am|pm)|midnight|noon)', s2_low)
    if t1 and t2 and t1.group(1) != t2.group(1):
        return {'contradict': True, 'type':'time', 'suggestion': f'Unify deadline time ({t1.group(1)} vs {t2.group(1)})'}
    return {'contradict': False}

@app.post('/analyze')
async def analyze(payload: dict):
    file_ids = payload.get('file_ids') or []
    user_id = payload.get('user_id') or 'demo-user'
    # charge credits (1 credit per doc)
    cost = len(file_ids)
    if USER_CREDITS.get(user_id, 0) < cost:
        return JSONResponse({'error':'insufficient credits'}, status_code=402)
    USER_CREDITS[user_id] -= cost

    docs = []
    for fid in file_ids:
        if fid not in FILE_STORE: continue
        path = FILE_STORE[fid]['path']
        text = extract_text_from_path(path)
        docs.append({'file_id': fid, 'filename': FILE_STORE[fid]['filename'], 'text': text, 'facts': extract_facts(text)})

    conflicts = []
    # Rule-based fact comparison
    for i in range(len(docs)):
        for j in range(i+1, len(docs)):
            d1 = docs[i]; d2 = docs[j]
            # compare attendance facts
            a1 = [f for f in d1['facts'] if f['type']=='attendance']
            a2 = [f for f in d2['facts'] if f['type']=='attendance']
            if a1 and a2 and a1[0]['value'] != a2[0]['value']:
                conflicts.append({
                    'doc_a': d1['filename'], 'doc_b': d2['filename'],
                    'excerpt_a': a1[0]['context'], 'excerpt_b': a2[0]['context'],
                    'conflict_type': 'attendance',
                    'suggestion': f'Pick one attendance value ({a1[0]["value"]} vs {a2[0]["value"]})',
                    'confidence': 0.9
                })
            # fallback: do lightweight semantic checks by scanning sentence pairs (mocked)
            # split into sentences
            sents1 = [s.strip() for s in re.split(r'[\\.\n]', d1['text']) if s.strip()]
            sents2 = [s.strip() for s in re.split(r'[\\.\n]', d2['text']) if s.strip()]
            # check top N sentence pairs
            for s1 in sents1[:10]:
                for s2 in sents2[:10]:
                    resp = mock_llm_contradiction(s1, s2)
                    if resp.get('contradict'):
                        conflicts.append({
                            'doc_a': d1['filename'], 'doc_b': d2['filename'],
                            'excerpt_a': s1, 'excerpt_b': s2,
                            'conflict_type': resp.get('type','semantic'),
                            'suggestion': resp.get('suggestion','Review these statements'),
                            'confidence': 0.75
                        })

    analysis_id = str(uuid.uuid4())
    result = {'analysis_id': analysis_id, 'user_id': user_id, 'file_ids': file_ids, 'conflicts': conflicts}
    ANALYSES[analysis_id] = result
    return JSONResponse(result)

@app.post('/pathway/webhook')
async def pathway_webhook(payload: dict):
    # payload: {doc_id, new_text}
    # For prototype: simply return notification acknowledged.
    return {'status':'received', 'payload': payload}

@app.post('/billing/charge')
async def billing_charge(payload: dict):
    user_id = payload.get('user_id','demo-user')
    amount = int(payload.get('amount',1))
    USER_CREDITS[user_id] = USER_CREDITS.get(user_id,0) - amount
    return {'user_id': user_id, 'remaining_credits': USER_CREDITS.get(user_id,0)}
