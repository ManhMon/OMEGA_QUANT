#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_9router.py - Unified Enterprise Patcher for 9router (Gemini, Antigravity, OpenCode & Codex)
=================================================================================================
Applies essential enterprise patches to 9router on Windows:
1. RTK Gemini & Antigravity Tool Support (recursive payload compression on response.result/output)
2. RTK OpenAI & Codex CLI Tool Support (unpack & compress function_call_output and custom_tool_call_output)
3. Headroom Gemini & Antigravity Tool Adapter (recursive target extraction for contents)
4. Headroom Codex CLI Tool Adapter (oa unpacks string, array, and object tool outputs)
5. Headroom compress_user_messages: true (forces user message compression in Headroom & DB)
6. Headroom Windows Zombie Process Fix (netstat 8787 port lookup + taskkill /F /T /PID)
7. Dashboard Token-Saver Stop Button Unlock (activates stop button when proxy reachable)

Usage:
  python scripts/patch_9router.py           # Apply patches with auto-backup
  python scripts/patch_9router.py --status  # Check current status of patches
  python scripts/patch_9router.py --restore # Restore original files from .bak
"""

import os
import sys
import glob
import json
import shutil
import sqlite3
import argparse
import subprocess
import tempfile

# -------------------------------------------------------------
# Patch Definitions for 8895.js
# -------------------------------------------------------------

# 1. RTK Gemini & Antigravity Recursive Tool Compression
NEEDLE_RTK = 'let d=Array.isArray(a.messages)?a.messages:Array.isArray(a.input)?a.input:null;'
RTK_RECURSIVE_LOGIC = 'let gGem=Array.isArray(a?.request?.contents)?a.request.contents:Array.isArray(a?.contents)?a.contents:null;if(gGem){let e={bytesBefore:0,bytesAfter:0,hits:[]};try{let cp=(o,d=0)=>{if(!o||"object"!=typeof o||d>4)return;for(let k of Object.keys(o)){if("string"==typeof o[k])o[k]=G(o[k],e,`gemini-tool-${k}`);else if(o[k]&&"object"==typeof o[k])cp(o[k],d+1);}};for(let it of gGem){if(Array.isArray(it?.parts)){for(let p of it.parts){if(p?.functionResponse){let r=p.functionResponse.response??p.functionResponse.output??p.functionResponse.result??p.functionResponse.content;if("string"==typeof r)p.functionResponse.response=G(r,e,"gemini-tool-response");else if(r&&"object"==typeof r)cp(r);}}}}}catch(err){console.warn("[RTK] compressGemini error:",err.message)}return e}'

# 2. RTK OpenAI & Codex CLI Tool Output Compression (custom_tool_call_output & function_call_output)
NEEDLE_RTK_OPENAI = 'if("function_call_output"===b.type){if("string"==typeof b.output)b.output=G(b.output,e,"openai-responses-string");else if(Array.isArray(b.output))for(let a=0;a<b.output.length;a++){let c=b.output[a];c&&"input_text"===c.type&&"string"==typeof c.text&&(c.text=G(c.text,e,"openai-responses-array"))}continue}'
REPLACE_RTK_OPENAI = 'if("function_call_output"===b.type||"custom_tool_call_output"===b.type){if("string"==typeof b.output)b.output=G(b.output,e,"openai-responses-string");else if(Array.isArray(b.output))for(let a=0;a<b.output.length;a++){let c=b.output[a];if(c&&"object"==typeof c&&"string"==typeof c.text)c.text=G(c.text,e,"openai-responses-array");else if("string"==typeof c)b.output[a]=G(c,e,"openai-responses-array")}else if(b.output&&"object"==typeof b.output&&"string"==typeof b.output.text){b.output.text=G(b.output.text,e,"openai-responses-object")}continue}'

# 3. Headroom Adapters Definition: oa (for openai-responses) + jG (for Gemini & Antigravity)
NEEDLE_J_DEF = 'function j(a){let b=a?.conversationState;'
OA_DEF = 'function oa(a){if(!Array.isArray(a?.input))return null;let c=[],d=[],e=(a,b,e,f={})=>{"string"==typeof b&&b.length>0&&(c.push({role:a,content:b,...f}),d.push(e))};"string"==typeof a.instructions&&a.instructions&&e("system",a.instructions,{object:a,key:"instructions"});for(let b of a.input){if(!b||"object"!=typeof b||Array.isArray(b))continue;let c=b.type||(b.role?"message":null);if("message"===c){let c=b.role||"user";if("string"==typeof b.content)e(c,b.content,{object:b,key:"content"});else if(Array.isArray(b.content))for(let a of b.content)a&&"object"==typeof a&&"string"==typeof a.text&&e(c,a.text,{object:a,key:"text"})}else if("function_call_output"===c||"custom_tool_call_output"===c){if("string"==typeof b.output&&b.output.length>0)e("tool",b.output,{object:b,key:"output"},b.call_id?{tool_call_id:b.call_id}:{});else if(Array.isArray(b.output))for(let a of b.output)a&&"object"==typeof a&&"string"==typeof a.text&&a.text.length>0&&e("tool",a.text,{object:a,key:"text"},b.call_id?{tool_call_id:b.call_id}:{});else if(b.output&&"object"==typeof b.output&&"string"==typeof b.output.text&&b.output.text.length>0)e("tool",b.output.text,{object:b.output,key:"text"},b.call_id?{tool_call_id:b.call_id}:{})}}return c.length>0?{messages:c,targets:d}:null}'
JG_DEF = 'function jG(a){let c=Array.isArray(a?.contents)?a.contents:Array.isArray(a?.request?.contents)?a.request.contents:null;if(!c)return null;let m=[],t=[];for(let it of c){let r=it?.role==="model"?"assistant":it?.role==="user"?"user":"system";if(Array.isArray(it?.parts)){for(let p of it.parts){if(typeof p?.text==="string"&&p.text.length>0){m.push({role:r,content:p.text});t.push({obj:p,key:"text"});}else if(p?.functionResponse){let s=p.functionResponse.response??p.functionResponse.output??p.functionResponse.result??p.functionResponse.content;let k=p.functionResponse.response?"response":p.functionResponse.output?"output":p.functionResponse.result?"result":"content";if(typeof s==="string"&&s.length>0){m.push({role:"tool",content:s});t.push({obj:p.functionResponse,key:k});}else if(s&&typeof s==="object"){let ex=(o,d=0)=>{if(!o||typeof o!=="object"||d>4)return;for(let k of Object.keys(o)){if(typeof o[k]==="string"&&o[k].length>0){m.push({role:"tool",content:o[k]});t.push({obj:o,key:k});}else if(o[k]&&"object"==typeof o[k])ex(o[k],d+1);}};ex(s);}}}}}return m.length>0?{messages:m,targets:t}:null}'

# 4. Telemetry & Metrics in h(a)
NEEDLE_H_VANILLA = 'let b=function(a){if(Array.isArray(a?.messages))return a.messages;if(Array.isArray(a?.input))return a.input;let b=j(a);return b?b.messages:null}(a)'
NEEDLE_H_JG_ONLY = 'let b=function(a){if(Array.isArray(a?.messages))return a.messages;if(Array.isArray(a?.input))return a.input;let b=j(a)||jG(a);return b?b.messages:null}(a)'
REPLACE_H_UNIFIED = 'let b=function(a){if(Array.isArray(a?.messages))return a.messages;if(Array.isArray(a?.input)){let o=oa(a);if(o)return o.messages;return a.input}let b=j(a)||jG(a);return b?b.messages:null}(a)'

# 5. Headroom Execution for Codex CLI (openai-responses)
TARGET_OPENAI_RESP = 'if("openai-responses"===m){if(Array.isArray(a?.input)&&a.input.some(a=>!(!a||"object"!=typeof a||Array.isArray(a))&&"string"==typeof a.type&&"message"!==a.type))return i(p,"skipped: openai-responses tool/reasoning input is not safe to compress"),null;let b=(0,f.Z)(g,a,!1);if(!Array.isArray(b?.messages))return i(p,"openai-responses request did not translate to messages[]"),null;let d=await k(c,b.messages,g,o,n,p||{});if(!d)return null;let e=(0,f.h)(g,{...b,input:void 0,messages:d.messages},!1);return Array.isArray(e?.input)&&(a.input=e.input),p&&(p.after=h(a)),d}'
REPLACE_OPENAI_RESP = 'if("openai-responses"===m){let b=oa(a);if(b){let d=await k(c,b.messages,g,o,n,p||{});if(!d||!function(a,b,c){if(!Array.isArray(b)||b.length!==a.messages.length)return i(c,"proxy response did not match openai-responses message count"),!1;let d=[];for(let e=0;e<a.messages.length;e++){let f=a.messages[e],g=b[e];if(!g||g.role!==f.role)return i(c,"proxy response did not preserve openai-responses message order"),!1;let h=function(a){let b=a?.content;if("string"==typeof b)return b;if(!Array.isArray(b))return null;let c=[];for(let a of b)"string"==typeof a?c.push(a):"string"==typeof a?.text&&c.push(a.text);return c.length>0?c.join("\\n"):null}(g);if(null===h)return i(c,"proxy response missing openai-responses text content"),!1;a.targets[e]&&d.push({target:a.targets[e],text:h})}for(let a of d)a.target.object[a.target.key]=a.text;return!0}(b,d.messages,p))return null;return p&&(p.after=h(a)),d}let e=(0,f.Z)(g,a,!1);if(!Array.isArray(e?.messages))return i(p,"openai-responses request did not translate to messages[]"),null;let j=await k(c,e.messages,g,o,n,p||{});if(!j)return null;let q=(0,f.h)(g,{...e,input:void 0,messages:j.messages},!1);return Array.isArray(q?.input)&&(a.input=q.input),p&&(p.after=h(a)),j}'

# 6. Headroom Execution for Gemini & Antigravity
NEEDLE_L = 'let b=Array.isArray(a.messages)?"messages":Array.isArray(a.input)?"input":null;'
HEADROOM_EXEC_LOGIC = 'if("gemini"===m||"gemini-cli"===m||"vertex"===m||"antigravity"===m||Array.isArray(a?.contents)||Array.isArray(a?.request?.contents)){let bg=jG(a);if(bg){let d=await k(c,bg.messages,g,o,n,p||{});if(d?.messages&&Array.isArray(d.messages)){for(let i=0;i<bg.targets.length&&i<d.messages.length;i++){let txt=typeof d.messages[i]?.content==="string"?d.messages[i].content:null;if(txt!==null)bg.targets[i].obj[bg.targets[i].key]=txt;}return p&&(p.after=h(a)),d;}return null;}}'

# 7. Headroom compress_user_messages: true in function k
NEEDLE_HEADROOM_USER_MSG = 'e&&(j.config={compress_user_messages:!0})'
REPLACE_HEADROOM_USER_MSG = 'j.config={compress_user_messages:!0}'

# 8. Stop Headroom Windows Process Tree (3016.js)
STOP_TARGET_QR = 'function q(a){if(!a||"number"!=typeof a)return!1;try{return process.kill(a,0),!0}catch{return!1}}function r(){let a=function(){try{if(e().existsSync(l))return parseInt(e().readFileSync(l,"utf8"),10)}catch{}return null}();return a&&q(a)?a:null}'
STOP_REPLACE_QR = 'function q(a){if(!a||"number"!=typeof a)return!1;try{return process.kill(a,0),!0}catch(e){return"EPERM"===e?.code}}function lp(){try{if("win32"===process.platform){let lines=(0,h.execSync)("netstat -ano -p tcp",{windowsHide:!0,timeout:3e3}).toString().split(/\\r?\\n/).filter(l=>l.includes(":8787")&&l.includes("LISTENING"));for(let l of lines){let p=parseInt(l.trim().split(/\\s+/).pop(),10);if(p&&q(p))return p}}}catch{}return null}function r(){let a=function(){try{if(e().existsSync(l))return parseInt(e().readFileSync(l,"utf8"),10)}catch{}return null}();if(a&&q(a))return a;let d=lp();if(d){try{o(),e().writeFileSync(l,String(d))}catch{}return d}return null}'

STOP_TARGET_T = 'function t(){let a=r();if(!a)return{stopped:!1,reason:"not_running"};try{return process.kill(a,"SIGTERM"),setTimeout(()=>{if(q(a))try{process.kill(a,"SIGKILL")}catch{}},2e3),p(),{stopped:!0,pid:a}}catch(b){p();let a=Error(`Failed to stop headroom proxy: ${b.message}`);throw a.code="STOP_FAILED",a}}'
STOP_REPLACE_T = 'function t(){let a=r();if(!a)return{stopped:!1,reason:"not_running"};try{try{process.kill(a,"SIGTERM")}catch{}if("win32"===process.platform)try{(0,h.execSync)(`taskkill /F /T /PID ${a}`,{windowsHide:!0,stdio:"ignore"})}catch{}setTimeout(()=>{if(q(a))try{process.kill(a,"SIGKILL")}catch{}},2e3),p();return{stopped:!0,pid:a}}catch(b){if("win32"===process.platform)try{(0,h.execSync)(`taskkill /F /T /PID ${a}`,{windowsHide:!0,stdio:"ignore"})}catch{}p();let a=Error(`Failed to stop headroom proxy: ${b.message}`);throw a.code="STOP_FAILED",a}}'

# 9. Dashboard Token-Saver Stop Button Fix
CLIENT_PAGE_TARGET = 'eH=eU&&!!p.managedPid'
CLIENT_PAGE_REPLACE = 'eH=eU&&(!!p.managedPid||eL)'

SERVER_PAGE_TARGET = 'aJ=aH&&!!n.managedPid'
SERVER_PAGE_REPLACE = 'aJ=aH&&(!!n.managedPid||aF)'


def locate_9router(custom_dir=None):
    if custom_dir and os.path.isdir(custom_dir):
        return custom_dir
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        p = os.path.join(appdata, 'npm', 'node_modules', '9router')
        if os.path.isdir(p):
            return p
    return None


def find_chunks(base_build):
    server_chunks = os.path.join(base_build, 'server', 'chunks')
    f_8895 = os.path.join(server_chunks, '8895.js')
    f_3016 = os.path.join(server_chunks, '3016.js')
    
    client_page = None
    server_page = None
    for root, _, files in os.walk(base_build):
        for f in files:
            if f.endswith('.js') and not f.endswith('.bak') and not '.bak_' in f:
                full = os.path.join(root, f)
                try:
                    with open(full, 'r', encoding='utf-8', errors='ignore') as fp:
                        txt = fp.read()
                    if CLIENT_PAGE_TARGET in txt or CLIENT_PAGE_REPLACE in txt:
                        client_page = full
                    if SERVER_PAGE_TARGET in txt or SERVER_PAGE_REPLACE in txt:
                        server_page = full
                except Exception:
                    pass

    return {
        '8895': f_8895 if os.path.isfile(f_8895) else None,
        '3016': f_3016 if os.path.isfile(f_3016) else None,
        'client_page': client_page,
        'server_page': server_page
    }


def patch_db_settings():
    db_path = os.path.expandvars(r'%APPDATA%\9router\db\data.sqlite')
    if not os.path.isfile(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute('SELECT data FROM settings WHERE id = 1').fetchone()
        if row:
            d = json.loads(row[0])
            if not d.get('headroomCompressUserMessages'):
                d['headroomCompressUserMessages'] = True
                conn.execute('UPDATE settings SET data = ? WHERE id = 1', (json.dumps(d),))
                conn.commit()
                conn.close()
                return True
            conn.close()
            return True
        conn.close()
    except Exception as err:
        print(f'  [WARN] Failed to patch DB settings: {err}')
    return False


def backup_file(path):
    bak = path + '.bak_enterprise'
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f'  [BACKUP] Created backup: {os.path.basename(bak)}')


def atomic_write(path, content):
    """Write patched file through same-directory temporary file with Windows retry."""
    import time
    directory = os.path.dirname(path) or '.'
    fd, temp_path = tempfile.mkstemp(prefix='.9router-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows transient lock retry on os.replace
        for attempt in range(10):
            try:
                os.replace(temp_path, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def check_status(files):
    print('\n=== 9ROUTER ENTERPRISE PATCH STATUS CHECK ===\n')

    p_8895 = files.get('8895')
    if p_8895 and os.path.isfile(p_8895):
        with open(p_8895, 'r', encoding='utf-8', errors='ignore') as f:
            c = f.read()
        rtk_gem_ok = 'gemini-tool-' in c and 'cp(r)' in c
        rtk_openai_ok = 'custom_tool_call_output' in c and 'openai-responses-array' in c
        jg_ok = 'function jG(a)' in c and 'let bg=jG(a)' in c
        oa_ok = 'function oa(a)' in c and 'let b=oa(a)' in c and 'Array.isArray(b.output)' in c
        headroom_user_msg_ok = 'j.config={compress_user_messages:!0}' in c
        print(f' 1. RTK Gemini & Antigravity Tool Compression:         [{"PATCHED" if rtk_gem_ok else "MISSING"}]')
        print(f' 2. RTK OpenAI & Codex CLI Tool Output Compression:     [{"PATCHED" if rtk_openai_ok else "MISSING"}]')
        print(f' 3. Headroom Gemini & Antigravity Tool Adapter (jG):    [{"PATCHED" if jg_ok else "MISSING"}]')
        print(f' 4. Headroom Codex CLI Adapter (oa unpacks outputs):    [{"PATCHED" if oa_ok else "MISSING"}]')
        print(f' 5. Headroom compress_user_messages: true (in code):   [{"PATCHED" if headroom_user_msg_ok else "MISSING"}]')
    else:
        print(' 1-5. 8895.js [NOT FOUND]')

    # Check DB settings
    db_path = os.path.expandvars(r'%APPDATA%\9router\db\data.sqlite')
    db_user_msg = False
    if os.path.isfile(db_path):
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute('SELECT data FROM settings WHERE id = 1').fetchone()
            if row:
                d = json.loads(row[0])
                db_user_msg = bool(d.get('headroomCompressUserMessages'))
            conn.close()
        except Exception:
            pass
    print(f' 5b.Headroom compress_user_messages in data.sqlite:     [{"ENABLED" if db_user_msg else "DISABLED"}]')

    p_3016 = files.get('3016')
    if p_3016 and os.path.isfile(p_3016):
        with open(p_3016, 'r', encoding='utf-8', errors='ignore') as f:
            c3 = f.read()
        stop_ok = STOP_REPLACE_QR in c3 and STOP_REPLACE_T in c3
        print(f' 6. Headroom Windows Zombie Process Tree Fix (3016.js): [{"PATCHED" if stop_ok else "MISSING"}]')
    else:
        print(' 6. 3016.js [NOT FOUND]')

    p_cli = files.get('client_page')
    cli_ok = False
    if p_cli and os.path.isfile(p_cli):
        with open(p_cli, 'r', encoding='utf-8', errors='ignore') as f:
            cli_ok = CLIENT_PAGE_REPLACE in f.read()

    p_srv = files.get('server_page')
    srv_ok = False
    if p_srv and os.path.isfile(p_srv):
        with open(p_srv, 'r', encoding='utf-8', errors='ignore') as f:
            srv_ok = SERVER_PAGE_REPLACE in f.read()

    dash_ok = cli_ok and (srv_ok or p_srv is None)
    print(f' 7. Dashboard Token-Saver Stop Button Unlock:           [{"PATCHED" if dash_ok else "MISSING"}]')
    print()


def apply_all(files, dry_run=False):
    print('\n=== APPLYING 9ROUTER ENTERPRISE PATCHES ===\n')
    success_count = 0
    total_count = 7

    p_8895 = files.get('8895')
    if not p_8895:
        print('  [FAIL] 8895.js not found!')
    else:
        with open(p_8895, 'r', encoding='utf-8') as f:
            c = f.read()
        modified = False

        # 1. RTK Gemini & Antigravity Recursive Tool Compression
        if 'gemini-tool-' in c and 'cp(r)' in c:
            print('  [OK] 1. RTK Gemini & Antigravity Recursive Compression already active')
            success_count += 1
        elif NEEDLE_RTK in c:
            c = c.replace(NEEDLE_RTK, RTK_RECURSIVE_LOGIC + NEEDLE_RTK, 1)
            modified = True
            print('  [SUCCESS] 1. RTK Gemini & Antigravity Recursive Compression applied')
            success_count += 1
        else:
            print('  [FAIL] 1. RTK needle not found in 8895.js')

        # 2. RTK OpenAI & Codex CLI Tool Output Compression
        if 'custom_tool_call_output' in c and 'openai-responses-array' in c:
            print('  [OK] 2. RTK OpenAI & Codex CLI Tool Output Compression already active')
            success_count += 1
        elif NEEDLE_RTK_OPENAI in c:
            c = c.replace(NEEDLE_RTK_OPENAI, REPLACE_RTK_OPENAI, 1)
            modified = True
            print('  [SUCCESS] 2. RTK OpenAI & Codex CLI Tool Output Compression applied')
            success_count += 1
        else:
            print('  [FAIL] 2. NEEDLE_RTK_OPENAI not found in 8895.js')

        # 3. Headroom Adapters Definition: oa(a) and jG(a)
        oa_jg_combined = OA_DEF + JG_DEF
        if 'function oa(a)' in c and 'Array.isArray(b.output)' in c and 'function jG(a)' in c:
            print('  [OK] 3. Headroom oa (with array tool output unpacking) & jG already defined')
            success_count += 1
        elif 'function oa(a)' in c and 'function jG(a)' in c:
            idx_oa = c.find('function oa(a)')
            idx_jg = c.find('function jG(a)', idx_oa)
            if idx_oa != -1 and idx_jg != -1:
                c = c[:idx_oa] + OA_DEF + c[idx_jg:]
                modified = True
                print('  [SUCCESS] 3. Upgraded oa(a) to unpack array and object tool outputs')
                success_count += 1
            else:
                print('  [FAIL] 3. Could not locate replacement boundary for oa(a)')
        elif 'function jG(a)' in c:
            idx_jg = c.find('function jG(a)')
            idx_j = c.find(NEEDLE_J_DEF, idx_jg)
            if idx_jg != -1 and idx_j != -1:
                c = c[:idx_jg] + oa_jg_combined + c[idx_j:]
                modified = True
                print('  [SUCCESS] 3. Upgraded definitions oa + jG')
                success_count += 1
            else:
                print('  [FAIL] 3. Could not locate replacement boundary for jG')
        elif NEEDLE_J_DEF in c:
            c = c.replace(NEEDLE_J_DEF, oa_jg_combined + NEEDLE_J_DEF, 1)
            modified = True
            print('  [SUCCESS] 3. Inserted oa and jG before function j(a)')
            success_count += 1
        else:
            print('  [FAIL] 3. Needle function j(a) not found')

        # 4. Telemetry h(a) & Codex CLI (openai-responses) execution
        if REPLACE_H_UNIFIED not in c:
            if NEEDLE_H_JG_ONLY in c:
                c = c.replace(NEEDLE_H_JG_ONLY, REPLACE_H_UNIFIED, 1)
                modified = True
            elif NEEDLE_H_VANILLA in c:
                c = c.replace(NEEDLE_H_VANILLA, REPLACE_H_UNIFIED, 1)
                modified = True

        # Update openai-responses execution
        if 'openai-responses message count' in c and 'let b=oa(a)' in c:
            print('  [OK] 4. Headroom Codex CLI Adapter (oa) execution already active')
            success_count += 1
        elif TARGET_OPENAI_RESP in c:
            c = c.replace(TARGET_OPENAI_RESP, REPLACE_OPENAI_RESP, 1)
            modified = True
            print('  [SUCCESS] 4. Headroom Codex CLI Adapter (oa) execution applied')
            success_count += 1
        else:
            print('  [FAIL] 4. TARGET_OPENAI_RESP needle not found in 8895.js')

        # Gemini & Antigravity execution block in async function l
        if 'let bg=jG(a)' in c and 'if("gemini"===m' in c:
            pass
        elif NEEDLE_L in c:
            c = c.replace(NEEDLE_L, HEADROOM_EXEC_LOGIC + NEEDLE_L, 1)
            modified = True

        # 5. Headroom compress_user_messages: true in function k
        db_ok = patch_db_settings()
        if REPLACE_HEADROOM_USER_MSG in c:
            print('  [OK] 5. Headroom compress_user_messages: true already active in 8895.js' + (' & data.sqlite' if db_ok else ''))
            success_count += 1
        elif NEEDLE_HEADROOM_USER_MSG in c:
            c = c.replace(NEEDLE_HEADROOM_USER_MSG, REPLACE_HEADROOM_USER_MSG, 1)
            modified = True
            print('  [SUCCESS] 5. Headroom compress_user_messages: true applied in 8895.js' + (' & data.sqlite' if db_ok else ''))
            success_count += 1
        else:
            print('  [WARN] 5. NEEDLE_HEADROOM_USER_MSG not found in 8895.js (DB updated: ' + str(db_ok) + ')')
            if db_ok:
                success_count += 1

        if modified and not dry_run:
            backup_file(p_8895)
            atomic_write(p_8895, c)

    # 6. Stop Headroom Windows Process Tree (3016.js)
    p_3016 = files.get('3016')
    if not p_3016:
        print('  [FAIL] 6. 3016.js not found!')
    else:
        with open(p_3016, 'r', encoding='utf-8') as f:
            c3 = f.read()
        mod3 = False
        if STOP_REPLACE_QR in c3 and STOP_REPLACE_T in c3:
            print('  [OK] 6. Stop Headroom Windows Process Tree already active')
            success_count += 1
        else:
            if STOP_TARGET_QR in c3:
                c3 = c3.replace(STOP_TARGET_QR, STOP_REPLACE_QR, 1)
                mod3 = True
            if STOP_TARGET_T in c3:
                c3 = c3.replace(STOP_TARGET_T, STOP_REPLACE_T, 1)
                mod3 = True
            if mod3 and not dry_run:
                backup_file(p_3016)
                atomic_write(p_3016, c3)
            if STOP_REPLACE_QR in c3 or STOP_REPLACE_T in c3:
                print('  [SUCCESS] 6. Stop Headroom Windows Process Tree active')
                success_count += 1
            else:
                print('  [FAIL] 6. Stop targets not found in 3016.js')

    # 7. Dashboard Token-Saver Stop Button Fix
    p_cli = files.get('client_page')
    p_srv = files.get('server_page')
    dash_ok = True

    if p_cli:
        with open(p_cli, 'r', encoding='utf-8') as f:
            cc = f.read()
        if CLIENT_PAGE_REPLACE not in cc:
            if CLIENT_PAGE_TARGET in cc:
                cc = cc.replace(CLIENT_PAGE_TARGET, CLIENT_PAGE_REPLACE, 1)
                if not dry_run:
                    backup_file(p_cli)
                    atomic_write(p_cli, cc)
            else:
                dash_ok = False

    if p_srv:
        with open(p_srv, 'r', encoding='utf-8') as f:
            cs = f.read()
        if SERVER_PAGE_REPLACE not in cs:
            if SERVER_PAGE_TARGET in cs:
                cs = cs.replace(SERVER_PAGE_TARGET, SERVER_PAGE_REPLACE, 1)
                if not dry_run:
                    backup_file(p_srv)
                    atomic_write(p_srv, cs)
            else:
                dash_ok = False

    if dash_ok:
        print('  [SUCCESS] 7. Dashboard Token-Saver Stop Button active')
        success_count += 1
    else:
        print('  [FAIL] 7. Dashboard Token-Saver Stop Button patch incomplete')

    print(f'\nResult: {success_count}/{total_count} enterprise patches active.')


def restore_all(files):
    print('\n=== RESTORING ORIGINAL FILES FROM BACKUP ===\n')
    for name, path in files.items():
        if not path:
            continue
        bak = path + '.bak_enterprise'
        if not os.path.exists(bak):
            bak = path + '.bak_20260917'
        if os.path.exists(bak):
            shutil.copy2(bak, path)
            print(f'  [RESTORED] {os.path.basename(path)} <= {os.path.basename(bak)}')
        else:
            print(f'  [NO BACKUP] {os.path.basename(path)}')
    print('\nRestore completed.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Unified Enterprise Patcher for 9router')
    parser.add_argument('--status', action='store_true', help='Check status of patches')
    parser.add_argument('--restore', action='store_true', help='Restore from backup')
    parser.add_argument('--dry-run', action='store_true', help='Check without writing files')
    parser.add_argument('--dir', type=str, default=None, help='Custom 9router directory')
    args = parser.parse_args(argv)

    base = locate_9router(args.dir)
    if not base:
        print('[ERROR] Could not locate 9router installation.')
        sys.exit(1)

    build_dir = os.path.join(base, 'app', '.next-cli-build')
    files = find_chunks(build_dir)

    if args.status:
        check_status(files)
    elif args.restore:
        restore_all(files)
    else:
        apply_all(files, dry_run=args.dry_run)
        check_status(files)


if __name__ == '__main__':
    main()
